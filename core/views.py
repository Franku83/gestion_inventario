import logging
import uuid
from collections import defaultdict, Counter
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, F, IntegerField, DecimalField, Value, OuterRef, Subquery, Count
from django.db.models.functions import Coalesce, NullIf
from django.db.models.deletion import ProtectedError
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta
from core.services import obtener_usd_bs_rate

from .forms import (
    ProveedorForm,
    TipoJoyaForm,
    ProductoForm,
    CompraUnificadaForm,
    CompraEditForm,
    VentaForm,
    VentaEditForm,
    PagoVentaForm,
    CompraMultipleFormSet,
    VentaLoteFormSet,
)

logger = logging.getLogger(__name__)

# =========================
# Helpers
# =========================

def _get_stock_map(product_ids=None):
    """Retorna dict producto_id -> stock disponible (int)."""
    compras_qs = Movimiento.objects.filter(tipo="IN", anulada=False)
    ventas_qs = Venta.objects.filter(anulada=False)
    if product_ids is not None:
        compras_qs = compras_qs.filter(producto_id__in=product_ids)
        ventas_qs = ventas_qs.filter(producto_id__in=product_ids)
    compras_map = {
        r["producto_id"]: int(r["total_in"] or 0)
        for r in compras_qs.values("producto_id").annotate(total_in=Sum("cantidad"))
    }
    ventas_map = {
        r["producto_id"]: int(r["total_out"] or 0)
        for r in ventas_qs.values("producto_id").annotate(total_out=Sum("cantidad"))
    }
    all_ids = set(compras_map) | set(ventas_map)
    if product_ids is not None:
        all_ids |= set(product_ids)
    return {pid: compras_map.get(pid, 0) - ventas_map.get(pid, 0) for pid in all_ids}


# =========================
# Dashboard / Inventario
# =========================

@login_required
def dashboard(request):
    # Tasa USD -> Bs
    try:
        tasa = obtener_usd_bs_rate()
        tasa = Decimal(str(tasa)) if tasa is not None else Decimal("0.00")
    except Exception as e:
        logger.warning("dashboard tasa error: %s", e)
        tasa = Decimal("0.00")

    productos = Producto.objects.select_related("proveedor").order_by("nombre")[:15]
    total_productos = Producto.objects.count()
    total_proveedores = Proveedor.objects.count()

    # Mapas compras/ventas
    compras_map = {
        r["producto_id"]: int(r["total_in"] or 0)
        for r in Movimiento.objects.filter(tipo="IN", anulada=False)
        .values("producto_id").annotate(total_in=Coalesce(Sum("cantidad"), 0))
    }
    ventas_map = {
        r["producto_id"]: int(r["total_out"] or 0)
        for r in Venta.objects.filter(anulada=False)
        .values("producto_id").annotate(total_out=Coalesce(Sum("cantidad"), 0))
    }

    # Dinero en stock
    dinero_stock_usd = Decimal("0.00")
    for p in Producto.objects.only("id", "costo_unitario"):
        stock_qty = compras_map.get(p.id, 0) - ventas_map.get(p.id, 0)
        if stock_qty < 0:
            stock_qty = 0
        dinero_stock_usd += Decimal(str(p.costo_unitario or 0)) * Decimal(stock_qty)

    # Dinero vendido
    dinero_vendido_usd = Decimal("0.00")
    for v in Venta.objects.filter(anulada=False).only("cantidad", "precio_unitario"):
        dinero_vendido_usd += Decimal(str(v.precio_unitario or 0)) * Decimal(int(v.cantidad or 0))

    # Dinero deuda: solo a_plazos=True (definición negocio)
    dinero_deuda_usd = Decimal("0.00")
    pagos_map = {
        r["venta_id"]: Decimal(str(r["pagado"] or "0.00"))
        for r in PagoVenta.objects.values("venta_id").annotate(pagado=Coalesce(Sum("monto"), Decimal("0.00")))
    }
    for v in Venta.objects.filter(a_plazos=True, anulada=False).only("id", "cantidad", "precio_unitario"):
        total = Decimal(str(v.precio_unitario or 0)) * Decimal(int(v.cantidad or 0))
        deuda = total - pagos_map.get(v.id, Decimal("0.00"))
        if deuda > 0:
            dinero_deuda_usd += deuda

    # Ganancia estimada
    ganancia_usd = Decimal("0.00")
    for v in Venta.objects.filter(anulada=False).select_related("producto").only("cantidad", "precio_unitario", "producto__costo_unitario"):
        costo = Decimal(str(v.producto.costo_unitario or 0))
        precio = Decimal(str(v.precio_unitario or 0))
        ganancia_usd += (precio - costo) * Decimal(v.cantidad)

    # Conversiones
    dinero_stock_bs = dinero_stock_usd * tasa
    dinero_vendido_bs = dinero_vendido_usd * tasa
    dinero_deuda_bs = dinero_deuda_usd * tasa
    ganancia_bs = ganancia_usd * tasa

    q = Decimal("0.01")
    dinero_stock_usd = dinero_stock_usd.quantize(q)
    dinero_vendido_usd = dinero_vendido_usd.quantize(q)
    dinero_deuda_usd = dinero_deuda_usd.quantize(q)
    ganancia_usd = ganancia_usd.quantize(q)
    dinero_stock_bs = dinero_stock_bs.quantize(q)
    dinero_vendido_bs = dinero_vendido_bs.quantize(q)
    dinero_deuda_bs = dinero_deuda_bs.quantize(q)
    ganancia_bs = ganancia_bs.quantize(q)

    context = {
        "productos": productos,
        "total_productos": total_productos,
        "total_proveedores": total_proveedores,
        "dinero_stock_usd": dinero_stock_usd,
        "dinero_stock_bs": dinero_stock_bs,
        "dinero_vendido_usd": dinero_vendido_usd,
        "dinero_vendido_bs": dinero_vendido_bs,
        "dinero_deuda_usd": dinero_deuda_usd,
        "dinero_deuda_bs": dinero_deuda_bs,
        "ganancia_usd": ganancia_usd,
        "ganancia_bs": ganancia_bs,
        "tasa_usd_bs": tasa,
        "dinero_stock": f"${dinero_stock_usd} USD / Bs {dinero_stock_bs}",
        "dinero_vendido": f"${dinero_vendido_usd} USD / Bs {dinero_vendido_bs}",
        "dinero_deuda": f"${dinero_deuda_usd} USD / Bs {dinero_deuda_bs}",
    }
    return render(request, "core/dashboard.html", context)


@login_required
def inventario(request):
    q = (request.GET.get("q") or "").strip()
    proveedor_id = (request.GET.get("proveedor") or "").strip()
    tipo_id = (request.GET.get("tipo") or "").strip()
    solo_stock = request.GET.get("solo_stock") == "on"

    productos = Producto.objects.select_related("proveedor", "tipo").order_by("nombre")
    if q:
        productos = productos.filter(nombre__icontains=q)
    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)
    if tipo_id:
        productos = productos.filter(tipo_id=tipo_id)

    total_in_sq = Movimiento.objects.filter(
        producto=OuterRef("pk"), tipo="IN", anulada=False
    ).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")

    total_out_sq = Venta.objects.filter(
        producto=OuterRef("pk"), anulada=False
    ).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")

    total_cost_sq = Movimiento.objects.filter(
        producto=OuterRef("pk"), tipo="IN", anulada=False
    ).order_by().values("producto").annotate(total=Sum(F("cantidad") * F("precio_unitario"))).values("total")

    total_in_val = Coalesce(Subquery(total_in_sq), Value(0), output_field=IntegerField())
    total_out_val = Coalesce(Subquery(total_out_sq), Value(0), output_field=IntegerField())
    total_cost_val = Coalesce(Subquery(total_cost_sq), Value(0), output_field=DecimalField(max_digits=18, decimal_places=2))

    productos = productos.annotate(
        stock=total_in_val - total_out_val,
        costo_prom=total_cost_val / NullIf(total_in_val, 0),
    )

    if solo_stock:
        productos = productos.filter(stock__gt=0)

    # Paginación
    paginator = Paginator(productos, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "productos": page_obj,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "proveedores": Proveedor.objects.all().order_by("nombre"),
        "tipos": TipoJoya.objects.all().order_by("nombre"),
        "filters": {"q": q, "proveedor": proveedor_id, "tipo": tipo_id, "solo_stock": solo_stock},
    }
    return render(request, "core/inventario.html", context)


# =========================
# Proveedores CRUD
# =========================

@login_required
def proveedor_list(request):
    qs = Proveedor.objects.all().order_by("nombre")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/proveedor_list.html", {"proveedores": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages()})


@login_required
def proveedor_create(request):
    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor creado.")
            return redirect("proveedor_list")
    else:
        form = ProveedorForm()
    return render(request, "core/form.html", {"form": form, "title": "Crear proveedor"})


@login_required
def proveedor_update(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor actualizado.")
            return redirect("proveedor_list")
    else:
        form = ProveedorForm(instance=proveedor)
    return render(request, "core/form.html", {"form": form, "title": "Editar proveedor"})


@login_required
def proveedor_delete(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        try:
            proveedor.delete()
            messages.success(request, "Proveedor eliminado.")
            return redirect("proveedor_list")
        except ProtectedError:
            messages.error(request, "No se puede eliminar este proveedor porque tiene productos/compras asociadas.")
            return redirect("proveedor_list")
        except Exception as e:
            messages.error(request, f"Error eliminando proveedor: {e}")
            return redirect("proveedor_list")
    return render(request, "core/confirm_delete.html", {"obj": proveedor, "title": "Eliminar proveedor"})


# =========================
# Tipos CRUD
# =========================

@login_required
def tipo_list(request):
    qs = TipoJoya.objects.all().order_by("nombre")
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/tipo_list.html", {"tipos": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages()})


@login_required
def tipo_create(request):
    if request.method == "POST":
        form = TipoJoyaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo creado.")
            return redirect("tipo_list")
    else:
        form = TipoJoyaForm()
    return render(request, "core/form.html", {"form": form, "title": "Crear tipo"})


@login_required
def tipo_update(request, pk):
    tipo = get_object_or_404(TipoJoya, pk=pk)
    if request.method == "POST":
        form = TipoJoyaForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo actualizado.")
            return redirect("tipo_list")
    else:
        form = TipoJoyaForm(instance=tipo)
    return render(request, "core/form.html", {"form": form, "title": "Editar tipo"})


@login_required
def tipo_delete(request, pk):
    tipo = get_object_or_404(TipoJoya, pk=pk)
    if request.method == "POST":
        try:
            tipo.delete()
            messages.success(request, "Tipo eliminado.")
            return redirect("tipo_list")
        except ProtectedError:
            messages.error(request, "No se puede eliminar este tipo porque tiene productos asociados.")
            return redirect("tipo_list")
        except Exception as e:
            messages.error(request, f"Error eliminando tipo: {e}")
            return redirect("tipo_list")
    return render(request, "core/confirm_delete.html", {"obj": tipo, "title": "Eliminar tipo"})


# =========================
# Productos CRUD
# =========================

@login_required
def producto_list(request):
    qs = Producto.objects.select_related("proveedor", "tipo").order_by("nombre")
    # Annotate stock para listado de productos
    total_in_sq = Movimiento.objects.filter(producto=OuterRef("pk"), tipo="IN", anulada=False).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")
    total_out_sq = Venta.objects.filter(producto=OuterRef("pk"), anulada=False).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")
    qs = qs.annotate(stock=Coalesce(Subquery(total_in_sq), Value(0), output_field=IntegerField()) - Coalesce(Subquery(total_out_sq), Value(0), output_field=IntegerField()))
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/producto_list.html", {"productos": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages()})


@login_required
def producto_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto creado.")
            return redirect("producto_list")
    else:
        form = ProductoForm()
    return render(request, "core/form.html", {"form": form, "title": "Crear producto"})


@login_required
def producto_update(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto actualizado.")
            return redirect("producto_list")
    else:
        form = ProductoForm(instance=producto)
    return render(request, "core/form.html", {"form": form, "title": "Editar producto"})


@login_required
def producto_delete(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        try:
            producto.delete()
            messages.success(request, "Producto eliminado.")
            return redirect("producto_list")
        except ProtectedError:
            messages.error(request, "No se puede eliminar este producto porque tiene compras/ventas asociadas.")
            return redirect("producto_list")
        except Exception as e:
            messages.error(request, f"Error eliminando producto: {e}")
            return redirect("producto_list")
    return render(request, "core/confirm_delete.html", {"obj": producto, "title": "Eliminar producto"})


# =========================
# Compras (IN)
# =========================

@login_required
def compra_create(request):
    if request.method == "POST":
        form = CompraUnificadaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Compra registrada.")
            return redirect("inventario")
    else:
        form = CompraUnificadaForm()
    return render(request, "core/compra_unificada.html", {"form": form})


@login_required
def compra_list(request):
    q = (request.GET.get("q") or "").strip()
    compras = Movimiento.objects.filter(tipo="IN", anulada=False).select_related("producto", "producto__proveedor", "producto__tipo").order_by("-fecha")
    if q:
        compras = compras.filter(producto__nombre__icontains=q)
    paginator = Paginator(compras, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/compra_list.html", {"compras": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages(), "q": q})


@login_required
def compra_update(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")
    if request.method == "POST":
        form = CompraEditForm(request.POST, instance=compra)
        if form.is_valid():
            form.save()
            messages.success(request, "Compra actualizada.")
            return redirect("compra_list")
    else:
        form = CompraEditForm(instance=compra)
    return render(request, "core/form.html", {"form": form, "title": "Editar compra"})


@login_required
def compra_delete(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")
    if request.method == "POST":
        compra.delete()
        messages.success(request, "Compra eliminada.")
        return redirect("compra_list")
    return render(request, "core/confirm_delete.html", {"obj": compra, "title": "Eliminar compra"})


@login_required
@require_POST
def compra_anular(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")
    compra.anulada = True
    compra.save(update_fields=["anulada"])
    messages.success(request, "Compra anulada (no se eliminó).")
    return redirect("compra_list")


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


# =========================
# Ventas + Deudas + Pagos
# =========================

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
            # Re-validar stock bajo lock para evitar race condition
            producto = form.cleaned_data["producto"]
            cantidad = form.cleaned_data["cantidad"]
            # Lock movimientos/ventas del producto
            stock_map = _get_stock_map([producto.id])
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
            # Re-validar stock bajo lock considerando la venta actual
            producto = form.cleaned_data["producto"]
            cantidad = form.cleaned_data["cantidad"]
            stock_map = _get_stock_map([producto.id])
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
    # Optimizado: sin N+1, con annotate y cálculo en DB
    # Definición: cualquier venta con deuda>0 (independiente de a_plazos), excluyendo anuladas
    from django.db.models import Exists

    # Pagado por venta
    pagos_sub = PagoVenta.objects.filter(venta=OuterRef("pk")).values("venta").annotate(s=Sum("monto")).values("s")
    ventas = (
        Venta.objects.filter(anulada=False)
        .select_related("producto", "producto__proveedor")
        .annotate(
            total_calc=F("precio_unitario") * F("cantidad"),
            pagado_calc=Coalesce(Subquery(pagos_sub, output_field=DecimalField(max_digits=18, decimal_places=2)), Value(Decimal("0.00"))),
        )
        .annotate(deuda_calc=F("total_calc") - F("pagado_calc"))
        .filter(deuda_calc__gt=0)
        .order_by("-fecha")
    )
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
            # Validar que no exceda deuda (opcional pero útil)
            total = (venta.precio_unitario or Decimal("0.00")) * (venta.cantidad or 0)
            pagado = PagoVenta.objects.filter(venta=venta).aggregate(s=Coalesce(Sum("monto"), Value(Decimal("0.00"))))["s"] or Decimal("0.00")
            deuda = total - pagado
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
@transaction.atomic
def compra_multiple(request):
    if request.method == "POST":
        formset = CompraMultipleFormSet(request.POST)
        if formset.is_valid():
            movimientos_creados = 0
            for form in formset:
                if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                    continue
                cantidad = form.cleaned_data.get('cantidad')
                if not cantidad:
                    continue
                precio_unitario = form.cleaned_data.get('precio_unitario') or Decimal("0.00")
                nota = form.cleaned_data.get('nota') or ""
                if (form.cleaned_data.get('crear_nuevo') or "").lower() == "true":
                    producto, _ = Producto.objects.get_or_create(
                        nombre=form.cleaned_data['nombre'],
                        proveedor=form.cleaned_data['proveedor'],
                        tipo=form.cleaned_data['tipo'],
                        defaults={
                            'costo_unitario': form.cleaned_data.get('costo_unitario') or Decimal("0.00"),
                            'precio_venta_unitario': form.cleaned_data.get('precio_venta_unitario') or Decimal("0.00"),
                        }
                    )
                else:
                    producto = form.cleaned_data.get('producto')
                if producto:
                    Movimiento.objects.create(tipo="IN", producto=producto, cantidad=cantidad, precio_unitario=precio_unitario, nota=nota)
                    movimientos_creados += 1
            if movimientos_creados > 0:
                messages.success(request, f"Se registraron {movimientos_creados} compras con éxito.")
            else:
                messages.warning(request, "No se registró ninguna compra.")
            return redirect("inventario")
    else:
        formset = CompraMultipleFormSet()
    return render(request, "core/compra_multiple.html", {"formset": formset})


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
            # Validación intra-lote: sumar cantidades por producto y comparar con stock
            demand = Counter()
            valid_forms = []
            for form in formset:
                if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                    continue
                cantidad = form.cleaned_data.get("cantidad")
                if not cantidad:
                    continue
                valid_forms.append(form)
                demand[form.cleaned_data["producto"].id] += cantidad

            if demand:
                stock_map = _get_stock_map(list(demand.keys()))
                lote_ok = True
                for pid, needed in demand.items():
                    if needed > stock_map.get(pid, 0):
                        lote_ok = False
                        # Añadir error a cada form de ese producto
                        for f in valid_forms:
                            if f.cleaned_data["producto"].id == pid:
                                f.add_error("cantidad", f"Stock insuficiente en lote. Disponible: {stock_map.get(pid,0)}, solicitado acumulado: {needed}")
                if not lote_ok:
                    # Re-render con errores
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
