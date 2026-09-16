import logging
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, F, IntegerField, DecimalField, Value, OuterRef, Subquery
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import render

from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta
from core.services import obtener_usd_bs_rate

logger = logging.getLogger(__name__)


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

# Proveedores CRUD → vive en proveedor/views.py (Sprint 1). Re-export compat.
from proveedor.views import (  # noqa: F401,E402
    proveedor_list,
    proveedor_create,
    proveedor_update,
    proveedor_delete,
)


# Tipos CRUD → vive en tipologia/views.py (Sprint 1). Re-export compat.
from tipologia.views import tipo_list, tipo_create, tipo_update, tipo_delete  # noqa: F401,E402

# Productos CRUD → vive en producto/views.py (Sprint 1). Re-export compat.
# Nota: hoy sin rutas en core/urls (pantalla muerta, solo vía inventario).
from producto.views import producto_list, producto_create, producto_update, producto_delete  # noqa: F401,E402


# Compras (IN) → vive en movimiento/views_compras.py (Sprint 1-2). Re-export compat.
# Sprint 2: compra_multiple y compra_delete eliminados (flujo único + solo anular).
from movimiento.views_compras import (  # noqa: F401,E402
    compra_anular,
    compra_create,
    compra_list,
    compra_update,
)
# Ventas + Deudas + Pagos → vive en movimiento/views_ventas.py (Sprint 1). Re-export compat.
from movimiento.views_ventas import (  # noqa: F401,E402
    deudas_list,
    pago_create,
    pago_delete,
    resumen_mensual,
    venta_anular,
    venta_create,
    venta_detalle,
    venta_lote,
    venta_update,
)
