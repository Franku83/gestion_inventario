import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, F, IntegerField, DecimalField, Value, OuterRef, Subquery, Max, DateTimeField
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import render
from django.utils import timezone

from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta
from movimiento.services import ventas_con_deuda_qs
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

    total_productos = Producto.objects.count()
    total_proveedores = Proveedor.objects.count()

    # Sprint 4: listas accionables — top 5 deudas por cobrar
    top_deudas = list(ventas_con_deuda_qs()[:5])

    # Mapas compras/ventas/bajas (las bajas restan stock sin contar como venta)
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
    bajas_map = {
        r["producto_id"]: int(r["total_adj"] or 0)
        for r in Movimiento.objects.filter(tipo="ADJ", anulada=False)
        .values("producto_id").annotate(total_adj=Coalesce(Sum("cantidad"), 0))
    }

    # Dinero en stock
    dinero_stock_usd = Decimal("0.00")
    for p in Producto.objects.only("id", "costo_unitario"):
        stock_qty = compras_map.get(p.id, 0) - ventas_map.get(p.id, 0) - bajas_map.get(p.id, 0)
        if stock_qty < 0:
            stock_qty = 0
        dinero_stock_usd += Decimal(str(p.costo_unitario or 0)) * Decimal(stock_qty)

    # Dinero vendido
    dinero_vendido_usd = Decimal("0.00")
    for v in Venta.objects.filter(anulada=False).only("cantidad", "precio_unitario"):
        dinero_vendido_usd += Decimal(str(v.precio_unitario or 0)) * Decimal(int(v.cantidad or 0))

    # Dinero deuda: DEFINICIÓN ÚNICA Sprint 3 — misma que la bandeja
    # (ventas_con_deuda_qs): deuda = total - pagado > 0, no anuladas.
    # `a_plazos` es solo etiqueta Contado/A plazos, no filtro.
    dinero_deuda_usd = sum(
        (Decimal(str(v.deuda_calc or "0.00")) for v in ventas_con_deuda_qs()),
        Decimal("0.00"),
    )

    # Ganancia estimada
    ganancia_usd = Decimal("0.00")
    for v in Venta.objects.filter(anulada=False).select_related("producto").only("cantidad", "precio_unitario", "producto__costo_unitario"):
        costo = Decimal(str(v.producto.costo_unitario or 0))
        precio = Decimal(str(v.precio_unitario or 0))
        ganancia_usd += (precio - costo) * Decimal(v.cantidad)

    # Sprint 4: top 5 stock inmovilizado (stock>0 sin ventas en 90 días, por valor)
    limite = timezone.now() - timedelta(days=90)
    con_ventas_recientes = set(
        Venta.objects.filter(anulada=False, fecha__gte=limite).values_list("producto_id", flat=True)
    )
    inmovilizado = []
    for p in Producto.objects.select_related("proveedor").only("id", "nombre", "costo_unitario", "proveedor__nombre"):
        stock_qty = compras_map.get(p.id, 0) - ventas_map.get(p.id, 0) - bajas_map.get(p.id, 0)
        if stock_qty > 0 and p.id not in con_ventas_recientes:
            costo = Decimal(str(p.costo_unitario or 0))
            inmovilizado.append({"producto": p, "stock": stock_qty, "valor": costo * Decimal(stock_qty)})
    inmovilizado.sort(key=lambda r: r["valor"], reverse=True)
    top_inmovilizado = inmovilizado[:5]

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
        "top_deudas": top_deudas,
        "top_inmovilizado": top_inmovilizado,
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
    # Sprint 4: por defecto solo con stock (práctico). El form envía off/on explícito.
    solo_stock = request.GET.get("solo_stock", "on") == "on"

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

    total_adj_sq = Movimiento.objects.filter(
        producto=OuterRef("pk"), tipo="ADJ", anulada=False
    ).order_by().values("producto").annotate(total=Sum("cantidad")).values("total")

    ultimo_ingreso_sq = Movimiento.objects.filter(
        producto=OuterRef("pk"), tipo="IN", anulada=False
    ).order_by().values("producto").annotate(ult=Max("fecha")).values("ult")

    ultima_venta_sq = Venta.objects.filter(
        producto=OuterRef("pk"), anulada=False
    ).order_by().values("producto").annotate(ult=Max("fecha")).values("ult")

    total_in_val = Coalesce(Subquery(total_in_sq), Value(0), output_field=IntegerField())
    total_out_val = Coalesce(Subquery(total_out_sq), Value(0), output_field=IntegerField())
    total_adj_val = Coalesce(Subquery(total_adj_sq), Value(0), output_field=IntegerField())
    total_cost_val = Coalesce(Subquery(total_cost_sq), Value(0), output_field=DecimalField(max_digits=18, decimal_places=2))

    productos = productos.annotate(
        stock=total_in_val - total_out_val - total_adj_val,
        costo_prom=total_cost_val / NullIf(total_in_val, 0),
        ultimo_ingreso=Subquery(ultimo_ingreso_sq, output_field=DateTimeField()),
        ultima_venta=Subquery(ultima_venta_sq, output_field=DateTimeField()),
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


# Compras (IN) + bajas (ADJ) → vive en movimiento/views_compras.py (Sprint 1-2). Re-export compat.
# Sprint 2: compra_multiple y compra_delete eliminados (flujo único + solo anular).
from movimiento.views_compras import (  # noqa: F401,E402
    ajuste_anular,
    ajuste_create,
    ajuste_list,
    compra_anular,
    compra_create,
    compra_list,
    compra_update,
)
# Ventas + Deudas + Pagos → vive en movimiento/views_ventas.py (Sprint 1-3). Re-export compat.
# Sprint 3: venta_lote eliminado (flujo único venta_create).
from movimiento.views_ventas import (  # noqa: F401,E402
    deudas_list,
    pago_create,
    pago_delete,
    resumen_mensual,
    venta_anular,
    venta_create,
    venta_detalle,
    venta_update,
)
