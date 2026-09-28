from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from movimiento.forms import AjusteBajaForm, CompraForm, CompraFormSet
from movimiento.models import Movimiento
from movimiento.services import get_stock_map
from producto.models import Producto


@login_required
@transaction.atomic
def compra_create(request):
    """Flujo único de compras (Sprint 2): formset 1 fila + botón agregar.

    Cada fila acepta producto existente o creación inline (crear_nuevo).
    """
    if request.method == "POST":
        formset = CompraFormSet(request.POST)
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
                messages.success(request, f"Se {'registró 1 compra' if movimientos_creados == 1 else f'registraron {movimientos_creados} compras'} con éxito.")
            else:
                messages.warning(request, "No se registró ninguna compra.")
            return redirect("inventario")
    else:
        initial = None
        pid = (request.GET.get("producto") or "").strip()
        if pid.isdigit() and Producto.objects.filter(pk=int(pid), activo=True).exists():
            initial = [{"producto": int(pid)}]
        formset = CompraFormSet(initial=initial)
    return render(request, "core/compra_form.html", {"formset": formset})


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
        form = CompraForm(request.POST, instance=compra)
        if form.is_valid():
            form.save()
            messages.success(request, "Compra actualizada.")
            return redirect("compra_list")
    else:
        form = CompraForm(instance=compra)
    return render(request, "core/form.html", {"form": form, "title": "Editar compra"})


@login_required
@require_POST
def compra_anular(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")
    compra.anulada = True
    compra.save(update_fields=["anulada"])
    messages.success(request, "Compra anulada (no se eliminó).")
    return redirect("compra_list")


@login_required
@transaction.atomic
def ajuste_create(request, pk):
    """Baja de stock sin vender. Crea Movimiento ADJ (reversible vía anular)."""
    producto = get_object_or_404(Producto.objects.select_related("proveedor", "tipo"), pk=pk)
    stock = get_stock_map([producto.id]).get(producto.id, 0)
    if request.method == "POST":
        form = AjusteBajaForm(request.POST, producto=producto)
        if form.is_valid():
            stock_now = get_stock_map([producto.id]).get(producto.id, 0)
            cantidad = form.cleaned_data["cantidad"]
            if cantidad > stock_now:
                form.add_error("cantidad", f"Solo hay {stock_now} en stock.")
            else:
                Movimiento.objects.create(
                    tipo="ADJ",
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=Decimal("0.00"),
                    nota=f"BAJA: {form.cleaned_data['motivo']}",
                )
                messages.success(request, f"Baja registrada: {cantidad} x {producto.nombre}.")
                return redirect("inventario")
    else:
        form = AjusteBajaForm(producto=producto)
    return render(request, "core/baja_form.html", {"form": form, "producto": producto, "stock": stock})


@login_required
def ajuste_list(request):
    ajustes = (
        Movimiento.objects.filter(tipo="ADJ")
        .select_related("producto", "producto__proveedor")
        .order_by("-fecha")
    )
    paginator = Paginator(ajustes, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "core/ajuste_list.html", {"ajustes": page_obj, "page_obj": page_obj, "is_paginated": page_obj.has_other_pages()})


@login_required
@require_POST
def ajuste_anular(request, pk):
    ajuste = get_object_or_404(Movimiento, pk=pk, tipo="ADJ")
    ajuste.anulada = True
    ajuste.save(update_fields=["anulada"])
    messages.success(request, "Baja anulada (stock devuelto).")
    return redirect("ajuste_list")
