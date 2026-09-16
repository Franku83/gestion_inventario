from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.shortcuts import render, redirect, get_object_or_404

from tipologia.forms import TipoJoyaForm
from tipologia.models import TipoJoya


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
