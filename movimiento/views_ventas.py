import uuid
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from movimiento.forms import PagoVentaForm, VentaEditForm, VentaForm, VentaLoteFormSet
from movimiento.models import PagoVenta, Venta
from movimiento.services import get_deuda, get_stock_map, validar_stock_lote, ventas_con_deuda_qs
from producto.models import Producto


@login_required
@require_POST
def venta_anular(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    venta.anulada = True
    venta.save(update_fields=["anulada"])
    messages.success(request, "Venta anulada (no se eliminó).")
    next_url = request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("venta_detalle", pk=pk)


@login_required
@transaction.atomic
def venta_create(request):
    used_tokens = request.session.get("used_venta_tokens", [])
    if request.method == "POST":
        token = request.POST.get("idempotency_token", "")
        if token in used_tokens:
            messages.warning(request, "Esta venta ya fue registrada.")
            return redirect("dashboard")
        form = VentaForm(request.POST)
        if form.is_valid():
            # Re-validar stock con la fuente única para evitar race condition
            producto = form.cleaned_data["producto"]
            cantidad = form.cleaned_data["cantidad"]
            stock_map = get_stock_map([producto.id])
            if cantidad > stock_map.get(producto.id, 0):
                form.add_error("cantidad", f"Stock insuficiente. Disponible: {stock_map.get(producto.id, 0)}")
            else:
                venta = form.save(commit=False)
                venta.save()
                pago_inicial = form.cleaned_data.get("pago_inicial") or Decimal("0.00")
                if pago_inicial > 0:
                    PagoVenta.objects.create(venta=venta, monto=pago_inicial, fecha=venta.fecha, nota="Pago inicial")
                used_tokens.append(token)
                if len(used_tokens) > 50:
                    used_tokens = used_tokens[-50:]
                request.session["used_venta_tokens"] = used_tokens
                messages.success(request, "Venta registrada.")
                return redirect("dashboard")
    else:
        form = VentaForm()

    idempotency_token = str(uuid.uuid4())
    productos = Producto.objects.filter(activo=True)
    precios_productos = {p.id: float(p.precio_venta_unitario) for p in productos}
    return render(request, "core/venta_form.html", {"form": form, "precios_productos": precios_productos, "idempotency_token": idempotency_token})


@login_required
@transaction.atomic
def venta_update(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        form = VentaEditForm(request.POST, instance=venta)
        if form.is_valid():
            # Re-validar stock considerando la venta actual
            producto = form.cleaned_data["producto"]
            cantidad = form.cleaned_data["cantidad"]
            stock_map = get_stock_map([producto.id])
            stock_disp = stock_map.get(producto.id, 0)
            # Si es mismo producto, devolver stock de la venta actual
            if venta.producto_id == producto.id and not venta.anulada:
                stock_disp += venta.cantidad
            if cantidad > stock_disp:
                form.add_error("cantidad", f"Stock insuficiente. Disponible: {stock_disp}")
            else:
                form.save()
                messages.success(request, "Venta/Deuda actualizada.")
                return redirect("venta_detalle", pk=venta.pk)
    else:
        form = VentaEditForm(instance=venta)

    productos = Producto.objects.filter(activo=True)
    precios_productos = {p.id: float(p.precio_venta_unitario) for p in productos}
    return render(request, "core/venta_form.html", {"form": form, "precios_productos": precios_productos, "title": "Editar Venta/Deuda", "obj": venta})


@login_required
def deudas_list(request):
    # Fuente única: movimiento.services.ventas_con_deuda_qs() (deuda>0, no anuladas, sin N+1)
    ventas = ventas_con_deuda_qs()
    paginator = Paginator(ventas, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/deudas_list.html", {"ventas": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages()})


@login_required
def venta_detalle(request, pk):
    venta = get_object_or_404(Venta.objects.select_related("producto", "producto__proveedor", "producto__tipo"), pk=pk)
    pagos = PagoVenta.objects.filter(venta=venta).order_by("-fecha")
    total = (venta.precio_unitario or Decimal("0.00")) * (venta.cantidad or 0)
    pagado = pagos.aggregate(s=Coalesce(Sum("monto"), Value(Decimal("0.00"))))["s"] or Decimal("0.00")
    deuda = total - pagado
    if deuda < 0:
        deuda = Decimal("0.00")
    return render(request, "core/venta_detalle.html", {"venta": venta, "pagos": pagos, "total": total, "pagado": pagado, "deuda": deuda})


@login_required
@transaction.atomic
def pago_create(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)
    if venta.anulada:
        messages.error(request, "No se puede abonar una venta anulada.")
        return redirect("venta_detalle", pk=venta.id)
    if request.method == "POST":
        form = PagoVentaForm(request.POST)
        if form.is_valid():
            monto = form.cleaned_data["monto"]
            deuda = get_deuda(venta)
            if monto > deuda:
                messages.warning(request, f"El abono excede la deuda pendiente (${deuda}). Se registrará igual.")
            pago = form.save(commit=False)
            pago.venta = venta
            pago.save()
            messages.success(request, "Pago registrado.")
            return redirect("venta_detalle", pk=venta.id)
    else:
        form = PagoVentaForm()
    return render(request, "core/abono_form.html", {"form": form, "venta": venta})


@login_required
def pago_delete(request, pk):
    pago = get_object_or_404(PagoVenta, pk=pk)
    venta_id = pago.venta_id
    if request.method == "POST":
        pago.delete()
        messages.success(request, "Pago eliminado.")
        return redirect("venta_detalle", pk=venta_id)
    return render(request, "core/confirm_delete.html", {"obj": pago, "title": "Eliminar pago"})


@login_required
def resumen_mensual(request):
    anio_actual = timezone.now().year
    try:
        anio = int(request.GET.get("anio", anio_actual))
    except (TypeError, ValueError):
        anio = anio_actual

    ventas = Venta.objects.filter(anulada=False, fecha__year=anio).select_related("producto")
    meses_data = defaultdict(lambda: {"num_ventas": 0, "total_vendido": Decimal("0"), "total_costo": Decimal("0")})
    for v in ventas:
        mes = v.fecha.month
        meses_data[mes]["num_ventas"] += 1
        meses_data[mes]["total_vendido"] += (v.precio_unitario or Decimal("0")) * (v.cantidad or 0)
        meses_data[mes]["total_costo"] += (v.producto.costo_unitario or Decimal("0")) * (v.cantidad or 0)

    nombres_mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    resumen = []
    for mes in sorted(meses_data.keys()):
        d = meses_data[mes]
        total_vendido = d["total_vendido"]
        total_costo = d["total_costo"]
        ganancia = total_vendido - total_costo
        margen = float(ganancia / total_vendido * 100) if total_vendido > 0 else 0.0
        resumen.append({
            "mes": mes,
            "mes_nombre": nombres_mes[mes],
            "num_ventas": d["num_ventas"],
            "total_vendido": float(total_vendido),
            "total_costo": float(total_costo),
            "ganancia": float(ganancia),
            "margen": round(margen, 1),
        })

    total_general_vendido = sum(r["total_vendido"] for r in resumen)
    total_general_costo = sum(r["total_costo"] for r in resumen)
    total_general_ganancia = total_general_vendido - total_general_costo
    total_general_margen = round(total_general_ganancia / total_general_vendido * 100, 1) if total_general_vendido > 0 else 0.0
    total_general_ventas = sum(r["num_ventas"] for r in resumen)

    anios = sorted({d.year for d in Venta.objects.filter(anulada=False).dates("fecha", "year")})
    if not anios:
        anios = [anio_actual]

    return render(request, "core/resumen_mensual.html", {
        "resumen": resumen,
        "anio": anio,
        "anios": anios,
        "total_general_vendido": total_general_vendido,
        "total_general_costo": total_general_costo,
        "total_general_ganancia": total_general_ganancia,
        "total_general_margen": total_general_margen,
        "total_general_ventas": total_general_ventas,
    })


@login_required
@transaction.atomic
def venta_lote(request):
    used_tokens = request.session.get("used_venta_tokens", [])
    if request.method == "POST":
        token = request.POST.get("idempotency_token", "")
        if token in used_tokens:
            messages.warning(request, "Este lote de ventas ya fue registrado.")
            return redirect("dashboard")
        formset = VentaLoteFormSet(request.POST)
        if formset.is_valid():
            # Validación intra-lote vía servicio único (Sprint 1)
            valid_forms = []
            items = []
            for form in formset:
                if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                    continue
                cantidad = form.cleaned_data.get("cantidad")
                if not cantidad:
                    continue
                valid_forms.append(form)
                items.append((form.cleaned_data["producto"].id, cantidad))

            faltantes = validar_stock_lote(items) if items else {}
            if faltantes:
                for f in valid_forms:
                    pid = f.cleaned_data["producto"].id
                    if pid in faltantes:
                        info = faltantes[pid]
                        f.add_error("cantidad", f"Stock insuficiente en lote. Disponible: {info['disponible']}, solicitado acumulado: {info['pedido']}")
                productos = Producto.objects.filter(activo=True)
                precios_productos = {p.id: float(p.precio_venta_unitario) for p in productos}
                return render(request, "core/venta_lote.html", {"formset": formset, "precios_productos": precios_productos, "idempotency_token": token})

            ventas_creadas = 0
            for form in valid_forms:
                Venta.objects.create(
                    producto=form.cleaned_data["producto"],
                    cantidad=form.cleaned_data["cantidad"],
                    precio_unitario=form.cleaned_data.get("precio_unitario") or Decimal("0.00"),
                    cliente=form.cleaned_data.get("cliente") or "",
                    nota=form.cleaned_data.get("nota") or "",
                )
                ventas_creadas += 1

            if ventas_creadas > 0:
                used_tokens.append(token)
                if len(used_tokens) > 50:
                    used_tokens = used_tokens[-50:]
                request.session["used_venta_tokens"] = used_tokens
                messages.success(request, f"Se registraron {ventas_creadas} ventas con éxito.")
            else:
                messages.warning(request, "No se registró ninguna venta.")
            return redirect("dashboard")
    else:
        formset = VentaLoteFormSet()

    productos = Producto.objects.filter(activo=True)
    precios_productos = {p.id: float(p.precio_venta_unitario) for p in productos}
    idempotency_token = str(uuid.uuid4())
    return render(request, "core/venta_lote.html", {"formset": formset, "precios_productos": precios_productos, "idempotency_token": idempotency_token})
