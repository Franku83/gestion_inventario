from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Case, When, IntegerField, Value, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta

from .forms import (
    ProveedorForm, TipoJoyaForm, ProductoForm,
    CompraForm, VentaForm, PagoVentaForm,
    CompraUnificadaForm
)


from core.forms import CompraUnificadaForm

# ---------------------------
# Helpers: stock y listados
# ---------------------------
def productos_con_stock_qs():
    # Entradas (compras)
    entradas = Coalesce(
        Sum(
            Case(
                When(movimientos__tipo="IN", then=F("movimientos__cantidad")),
                default=Value(0),
                output_field=IntegerField(),
            )
        ),
        0,
    )

    # Salidas: ventas
    salidas = Coalesce(Sum("ventas__cantidad"), 0)

    return Producto.objects.select_related("proveedor", "tipo").annotate(
        entradas=entradas,
        salidas=salidas
    ).annotate(
        stock=F("entradas") - F("salidas")
    )


# ---------------------------
# Dashboard
# ---------------------------
def dashboard(request):
    productos = productos_con_stock_qs().filter(stock__gt=0, activo=True).order_by("nombre")

    dinero_stock = productos.aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("stock") * F("costo_unitario"),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    dinero_vendido = Venta.objects.aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("cantidad") * F("precio_unitario"),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    pagos_total = PagoVenta.objects.aggregate(
        total=Coalesce(Sum("monto"), Decimal("0.00"))
    )["total"]

    # deuda total = total vendido - pagado (solo ventas a plazos cuentan deuda)
    total_plazos = Venta.objects.filter(a_plazos=True).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("cantidad") * F("precio_unitario"),
                    output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            ),
            Decimal("0.00")
        )
    )["total"]

    # pagos que corresponden a ventas a plazos
    pagos_plazos = PagoVenta.objects.filter(venta__a_plazos=True).aggregate(
        total=Coalesce(Sum("monto"), Decimal("0.00"))
    )["total"]

    deuda_total = total_plazos - pagos_plazos
    if deuda_total < 0:
        deuda_total = Decimal("0.00")

    return render(request, "core/dashboard.html", {
        "productos": productos,
        "dinero_stock": dinero_stock,
        "dinero_vendido": dinero_vendido,
        "dinero_deuda": deuda_total,
    })


# ---------------------------
# Inventario tipo farmacia
# ---------------------------
def inventario(request):
    q = request.GET.get("q", "").strip()
    qs = productos_con_stock_qs().filter(stock__gt=0, activo=True)

    if q:
        qs = qs.filter(nombre__icontains=q)

    qs = qs.order_by("nombre")[:120]
    return render(request, "core/inventario.html", {"productos": qs, "q": q})


# ---------------------------
# Compra (Entrada)
# ---------------------------
def compra_create(request):
    if request.method == "POST":
        form = CompraUnificadaForm(request.POST)
        if form.is_valid():
            _, _ = form.save()
            messages.success(request, "Compra registrada.")
            return redirect("inventario")
    else:
        form = CompraUnificadaForm()

    return render(request, "core/compra_unificada.html", {"form": form})


# ---------------------------
# Venta (con pago inicial)
# ---------------------------
def venta_create(request):
    if request.method == "POST":
        form = VentaForm(request.POST)
        if form.is_valid():
            venta = form.save(commit=False)

            # validar stock disponible
            stock_actual = productos_con_stock_qs().filter(id=venta.producto_id).values_list("stock", flat=True).first() or 0
            if venta.cantidad > stock_actual:
                messages.error(request, f"No hay suficiente stock. Stock actual: {stock_actual}.")
                return render(request, "core/form.html", {"form": form, "title": "Registrar venta"})

            venta.save()

            pago_inicial = form.cleaned_data.get("pago_inicial") or Decimal("0.00")
            if pago_inicial > 0:
                PagoVenta.objects.create(venta=venta, monto=pago_inicial, nota="Pago inicial")

            messages.success(request, "Venta registrada.")
            return redirect("inventario")
    else:
        form = VentaForm()
    return render(request, "core/form.html", {"form": form, "title": "Registrar venta"})


# ---------------------------
# Deudas + Abonos
# ---------------------------
def deudas_list(request):
    # ventas a plazos con deuda > 0
    ventas = Venta.objects.filter(a_plazos=True).select_related("producto", "producto__proveedor").order_by("-fecha")

    # Calculamos deuda en Python para mantenerlo simple
    ventas_con_deuda = [v for v in ventas if v.deuda > 0]

    return render(request, "core/deudas_list.html", {"ventas": ventas_con_deuda})


def abono_create(request, venta_id):
    venta = get_object_or_404(Venta.objects.select_related("producto"), id=venta_id)

    if request.method == "POST":
        form = PagoVentaForm(request.POST)
        if form.is_valid():
            pago = form.save(commit=False)
            pago.venta = venta

            # No permitir abonar más de lo que se debe
            if pago.monto > venta.deuda:
                messages.error(request, f"El abono excede la deuda. Deuda actual: {venta.deuda}")
            else:
                pago.save()
                messages.success(request, "Abono registrado.")
                return redirect("deudas_list")
    else:
        form = PagoVentaForm()

    return render(request, "core/abono_form.html", {"venta": venta, "form": form})


# ---------------------------
# CRUD Proveedor
# ---------------------------
def proveedor_list(request):
    q = request.GET.get("q", "").strip()
    qs = Proveedor.objects.all().order_by("nombre")
    if q:
        qs = qs.filter(nombre__icontains=q)
    return render(request, "core/proveedor_list.html", {"proveedores": qs, "q": q})


def proveedor_create(request):
    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor creado.")
            return redirect("proveedor_list")
    else:
        form = ProveedorForm()
    return render(request, "core/form.html", {"form": form, "title": "Nuevo proveedor"})


def proveedor_update(request, pk):
    obj = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor actualizado.")
            return redirect("proveedor_list")
    else:
        form = ProveedorForm(instance=obj)
    return render(request, "core/form.html", {"form": form, "title": "Editar proveedor"})


def proveedor_delete(request, pk):
    obj = get_object_or_404(Proveedor, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Proveedor eliminado.")
        return redirect("proveedor_list")
    return render(request, "core/confirm_delete.html", {"obj": obj, "title": "Eliminar proveedor"})


# ---------------------------
# CRUD Tipo
# ---------------------------
def tipo_list(request):
    q = request.GET.get("q", "").strip()
    qs = TipoJoya.objects.all().order_by("nombre")
    if q:
        qs = qs.filter(nombre__icontains=q)
    return render(request, "core/tipo_list.html", {"tipos": qs, "q": q})


def tipo_create(request):
    if request.method == "POST":
        form = TipoJoyaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo creado.")
            return redirect("tipo_list")
    else:
        form = TipoJoyaForm()
    return render(request, "core/form.html", {"form": form, "title": "Nuevo tipo"})


def tipo_update(request, pk):
    obj = get_object_or_404(TipoJoya, pk=pk)
    if request.method == "POST":
        form = TipoJoyaForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo actualizado.")
            return redirect("tipo_list")
    else:
        form = TipoJoyaForm(instance=obj)
    return render(request, "core/form.html", {"form": form, "title": "Editar tipo"})


def tipo_delete(request, pk):
    obj = get_object_or_404(TipoJoya, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Tipo eliminado.")
        return redirect("tipo_list")
    return render(request, "core/confirm_delete.html", {"obj": obj, "title": "Eliminar tipo"})


# ---------------------------
# CRUD Producto
# ---------------------------
def producto_list(request):
    q = request.GET.get("q", "").strip()
    proveedor_id = request.GET.get("proveedor", "").strip()
    tipo_id = request.GET.get("tipo", "").strip()

    qs = productos_con_stock_qs().order_by("nombre")

    if q:
        qs = qs.filter(nombre__icontains=q)
    if proveedor_id.isdigit():
        qs = qs.filter(proveedor_id=int(proveedor_id))
    if tipo_id.isdigit():
        qs = qs.filter(tipo_id=int(tipo_id))

    return render(request, "core/producto_list.html", {
        "productos": qs,
        "proveedores": Proveedor.objects.all().order_by("nombre"),
        "tipos": TipoJoya.objects.all().order_by("nombre"),
        "filters": {"q": q, "proveedor": proveedor_id, "tipo": tipo_id},
    })


def producto_create(request):
    if request.method == "POST":
        form = ProductoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto creado.")
            return redirect("producto_list")
    else:
        form = ProductoForm()
    return render(request, "core/form.html", {"form": form, "title": "Nuevo producto"})


def producto_update(request, pk):
    obj = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = ProductoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Producto actualizado.")
            return redirect("producto_list")
    else:
        form = ProductoForm(instance=obj)
    return render(request, "core/form.html", {"form": form, "title": "Editar producto"})


def producto_delete(request, pk):
    obj = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Producto eliminado.")
        return redirect("producto_list")
    return render(request, "core/confirm_delete.html", {"obj": obj, "title": "Eliminar producto"})
