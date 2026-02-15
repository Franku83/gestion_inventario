from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.db.models.deletion import ProtectedError
from django.views.decorators.http import require_POST

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
    PagoVentaForm,
)


# =========================
# Dashboard / Inventario
# =========================

from django.db.models import Count

from decimal import Decimal
from core.services import obtener_usd_bs_rate  # asegúrate que existe

def dashboard(request):
    # ---------- Tasa USD -> Bs ----------
    try:
        tasa = obtener_usd_bs_rate()  # Decimal
        if tasa is None:
            tasa = Decimal("0.00")
        tasa = Decimal(str(tasa))
    except Exception:
        tasa = Decimal("0.00")

    # ---------- Productos recientes / conteos ----------
    try:
        productos = Producto.objects.select_related("proveedor").all().order_by("nombre")[:15]
    except Exception:
        productos = []

    try:
        total_productos = Producto.objects.count()
    except Exception:
        total_productos = 0

    try:
        total_proveedores = Proveedor.objects.count()
    except Exception:
        total_proveedores = 0

    # ---------- Mapas: compras (IN, no anuladas) y ventas por producto ----------
    try:
        compras_map = {
            r["producto_id"]: int(r["total_in"] or 0)
            for r in (
                Movimiento.objects
                .filter(tipo="IN", anulada=False)   # tus campos existen :contentReference[oaicite:5]{index=5}
                .values("producto_id")
                .annotate(total_in=Coalesce(Sum("cantidad"), 0))
            )
        }
    except Exception:
        compras_map = {}

    try:
        ventas_map = {
            r["producto_id"]: int(r["total_out"] or 0)
            for r in (
                Venta.objects
                .values("producto_id")
                .annotate(total_out=Coalesce(Sum("cantidad"), 0))
            )
        }
    except Exception:
        ventas_map = {}

    # ---------- Dinero en stock (USD) = stock_qty * costo_unitario ----------
    dinero_stock_usd = Decimal("0.00")
    try:
        for p in Producto.objects.only("id", "costo_unitario"):
            total_in = compras_map.get(p.id, 0)
            total_out = ventas_map.get(p.id, 0)
            stock_qty = total_in - total_out
            if stock_qty < 0:
                stock_qty = 0

            costo = Decimal(str(p.costo_unitario or 0))
            dinero_stock_usd += (costo * Decimal(stock_qty))
    except Exception:
        dinero_stock_usd = Decimal("0.00")

    # ---------- Dinero vendido (USD) = sum(venta.cantidad * venta.precio_unitario) ----------
    dinero_vendido_usd = Decimal("0.00")
    try:
        dinero_vendido_usd = Decimal("0.00")
        # Evitamos ExpressionWrapper para que sea 100% compatible con SQLite/Postgres sin líos.
        for v in Venta.objects.only("cantidad", "precio_unitario"):
            dinero_vendido_usd += (Decimal(str(v.precio_unitario or 0)) * Decimal(int(v.cantidad or 0)))
    except Exception:
        dinero_vendido_usd = Decimal("0.00")

    # ---------- Dinero deuda (USD) = sum(venta.total - pagos) SOLO a_plazos=True ----------
    dinero_deuda_usd = Decimal("0.00")
    try:
        # pagos por venta en un solo query
        pagos_map = {
            r["venta_id"]: Decimal(str(r["pagado"] or "0.00"))
            for r in (
                PagoVenta.objects
                .values("venta_id")
                .annotate(pagado=Coalesce(Sum("monto"), Decimal("0.00")))
            )
        }

        for v in Venta.objects.filter(a_plazos=True).only("id", "cantidad", "precio_unitario"):
            total = Decimal(str(v.precio_unitario or 0)) * Decimal(int(v.cantidad or 0))
            pagado = pagos_map.get(v.id, Decimal("0.00"))
            deuda = total - pagado
            if deuda > 0:
                dinero_deuda_usd += deuda
    except Exception:
        dinero_deuda_usd = Decimal("0.00")

    # ---------- Conversiones a Bs ----------
    dinero_stock_bs = (dinero_stock_usd * tasa)
    dinero_vendido_bs = (dinero_vendido_usd * tasa)
    dinero_deuda_bs = (dinero_deuda_usd * tasa)

    # redondeo bonito
    q = Decimal("0.01")
    dinero_stock_usd = dinero_stock_usd.quantize(q)
    dinero_vendido_usd = dinero_vendido_usd.quantize(q)
    dinero_deuda_usd = dinero_deuda_usd.quantize(q)

    dinero_stock_bs = dinero_stock_bs.quantize(q)
    dinero_vendido_bs = dinero_vendido_bs.quantize(q)
    dinero_deuda_bs = dinero_deuda_bs.quantize(q)

    context = {
        "productos": productos,
        "total_productos": total_productos,
        "total_proveedores": total_proveedores,

        # NUEVO (USD + Bs)
        "dinero_stock_usd": dinero_stock_usd,
        "dinero_stock_bs": dinero_stock_bs,
        "dinero_vendido_usd": dinero_vendido_usd,
        "dinero_vendido_bs": dinero_vendido_bs,
        "dinero_deuda_usd": dinero_deuda_usd,
        "dinero_deuda_bs": dinero_deuda_bs,
        "tasa_usd_bs": tasa,

        # COMPATIBILIDAD con tu dashboard.html actual (usa dinero_stock, dinero_vendido, dinero_deuda) :contentReference[oaicite:6]{index=6}
        "dinero_stock": f"${dinero_stock_usd} USD / Bs {dinero_stock_bs}",
        "dinero_vendido": f"${dinero_vendido_usd} USD / Bs {dinero_vendido_bs}",
        "dinero_deuda": f"${dinero_deuda_usd} USD / Bs {dinero_deuda_bs}",
    }

    return render(request, "core/dashboard.html", context)

def inventario(request):
    q = (request.GET.get("q") or "").strip()
    proveedor_id = (request.GET.get("proveedor") or "").strip()
    tipo_id = (request.GET.get("tipo") or "").strip()
    solo_stock = request.GET.get("solo_stock") == "on"

    productos = Producto.objects.select_related("proveedor", "tipo").all().order_by("nombre")

    if q:
        productos = productos.filter(nombre__icontains=q)
    if proveedor_id:
        productos = productos.filter(proveedor_id=proveedor_id)
    if tipo_id:
        productos = productos.filter(tipo_id=tipo_id)

    # filtrar por stock en python si stock es @property
    productos_list = list(productos)
    if solo_stock:
        productos_list = [p for p in productos_list if getattr(p, "stock", 0) > 0]

    context = {
        "productos": productos_list,
        "proveedores": Proveedor.objects.all().order_by("nombre"),
        "tipos": TipoJoya.objects.all().order_by("nombre"),
        "filters": {"q": q, "proveedor": proveedor_id, "tipo": tipo_id, "solo_stock": solo_stock},
    }
    return render(request, "core/inventario.html", context)


# =========================
# Proveedores CRUD
# =========================

def proveedor_list(request):
    proveedores = Proveedor.objects.all().order_by("nombre")
    return render(request, "core/proveedor_list.html", {"proveedores": proveedores})


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


def proveedor_delete(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)

    if request.method == "POST":
        try:
            proveedor.delete()
            messages.success(request, "Proveedor eliminado.")
            return redirect("proveedor_list")
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar este proveedor porque tiene productos/compras asociadas. "
                "Primero elimina o cambia esos productos a otro proveedor."
            )
            return redirect("proveedor_list")
        except Exception as e:
            messages.error(request, f"Error eliminando proveedor: {e}")
            return redirect("proveedor_list")

    return render(request, "core/confirm_delete.html", {"obj": proveedor, "title": "Eliminar proveedor"})



# =========================
# Tipos CRUD
# =========================

def tipo_list(request):
    tipos = TipoJoya.objects.all().order_by("nombre")
    return render(request, "core/tipo_list.html", {"tipos": tipos})


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


def tipo_delete(request, pk):
    tipo = get_object_or_404(TipoJoya, pk=pk)
    if request.method == "POST":
        tipo.delete()
        messages.success(request, "Tipo eliminado.")
        return redirect("tipo_list")
    return render(request, "core/confirm_delete.html", {"obj": tipo, "title": "Eliminar tipo"})


# =========================
# Productos CRUD (opcional)
# =========================

def producto_list(request):
    productos = Producto.objects.select_related("proveedor", "tipo").all().order_by("nombre")
    return render(request, "core/producto_list.html", {"productos": productos})


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


def producto_delete(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    if request.method == "POST":
        try:
            producto.delete()
            messages.success(request, "Producto eliminado.")
            return redirect("producto_list")
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar este producto porque tiene compras/ventas asociadas. "
                "Si fue un error, edítalo en vez de borrarlo."
            )
            return redirect("producto_list")
        except Exception as e:
            messages.error(request, f"Error eliminando producto: {e}")
            return redirect("producto_list")

    return render(request, "core/confirm_delete.html", {"obj": producto, "title": "Eliminar producto"})


# =========================
# Compras (IN) - Unificada + Edit/Delete/List
# =========================

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


def compra_list(request):
    q = (request.GET.get("q") or "").strip()

    compras = (
    Movimiento.objects
    .filter(tipo="IN", anulada=False)  
    .select_related("producto", "producto__proveedor", "producto__tipo")
    .order_by("-fecha")
)


    if q:
        compras = compras.filter(producto__nombre__icontains=q)

    return render(request, "core/compra_list.html", {"compras": compras, "q": q})


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


def compra_delete(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")

    if request.method == "POST":
        compra.delete()
        messages.success(request, "Compra eliminada.")
        return redirect("compra_list")

    return render(request, "core/confirm_delete.html", {"obj": compra, "title": "Eliminar compra"})

@require_POST
def compra_anular(request, pk):
    compra = get_object_or_404(Movimiento, pk=pk, tipo="IN")
    compra.anulada = True
    compra.save(update_fields=["anulada"])
    messages.success(request, "Compra anulada (no se eliminó).")
    return redirect("compra_list")


# =========================
# Ventas + Deudas + Pagos
# =========================

def venta_create(request):
    if request.method == "POST":
        form = VentaForm(request.POST)
        if form.is_valid():
            venta = form.save(commit=False)
            venta.save()

            pago_inicial = form.cleaned_data.get("pago_inicial") or Decimal("0.00")
            if pago_inicial > 0:
                PagoVenta.objects.create(venta=venta, monto=pago_inicial, nota="Pago inicial")

            messages.success(request, "Venta registrada.")
            return redirect("dashboard")
    else:
        form = VentaForm()

    return render(request, "core/venta_form.html", {"form": form})


def deudas_list(request):
    # Ventas con deuda > 0 (calculado)
    ventas = Venta.objects.select_related("producto", "producto__proveedor").all().order_by("-fecha")
    con_deuda = []
    for v in ventas:
        total = (v.precio_unitario or Decimal("0.00")) * v.cantidad
        pagado = PagoVenta.objects.filter(venta=v).aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
        deuda = total - pagado
        if deuda > 0:
            v._total = total
            v._pagado = pagado
            v._deuda = deuda
            con_deuda.append(v)

    return render(request, "core/deudas_list.html", {"ventas": con_deuda})


def venta_detalle(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    pagos = PagoVenta.objects.filter(venta=venta).order_by("-fecha")

    total = (venta.precio_unitario or Decimal("0.00")) * venta.cantidad
    pagado = pagos.aggregate(s=Sum("monto"))["s"] or Decimal("0.00")
    deuda = total - pagado

    return render(request, "core/venta_detalle.html", {
        "venta": venta,
        "pagos": pagos,
        "total": total,
        "pagado": pagado,
        "deuda": deuda,
    })


def pago_create(request, venta_id):
    venta = get_object_or_404(Venta, pk=venta_id)

    if request.method == "POST":
        form = PagoVentaForm(request.POST)
        if form.is_valid():
            pago = form.save(commit=False)
            pago.venta = venta
            pago.save()
            messages.success(request, "Pago registrado.")
            return redirect("venta_detalle", pk=venta.id)
    else:
        form = PagoVentaForm()

    return render(request, "core/form.html", {"form": form, "title": "Registrar pago"})


def pago_delete(request, pk):
    pago = get_object_or_404(PagoVenta, pk=pk)
    venta_id = pago.venta_id

    if request.method == "POST":
        pago.delete()
        messages.success(request, "Pago eliminado.")
        return redirect("venta_detalle", pk=venta_id)

    return render(request, "core/confirm_delete.html", {"obj": pago, "title": "Eliminar pago"})
