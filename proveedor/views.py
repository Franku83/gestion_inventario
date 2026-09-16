from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.shortcuts import render, redirect, get_object_or_404

from proveedor.forms import ProveedorForm
from proveedor.models import Proveedor


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
