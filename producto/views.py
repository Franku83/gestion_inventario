from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect, get_object_or_404

from movimiento.models import Movimiento, Venta
from producto.forms import ProductoForm
from producto.models import Producto


@login_required
def producto_list(request):
    qs = Producto.objects.select_related("proveedor", "tipo").order_by("nombre")
    total_in_sq = Movimiento.objects.filter(producto=OuterRef("pk"), tipo="IN", anulada=False).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")
    total_out_sq = Venta.objects.filter(producto=OuterRef("pk"), anulada=False).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")
    total_adj_sq = Movimiento.objects.filter(producto=OuterRef("pk"), tipo="ADJ", anulada=False).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")
    qs = qs.annotate(stock=Coalesce(Subquery(total_in_sq), Value(0), output_field=IntegerField()) - Coalesce(Subquery(total_out_sq), Value(0), output_field=IntegerField()) - Coalesce(Subquery(total_adj_sq), Value(0), output_field=IntegerField()))
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
