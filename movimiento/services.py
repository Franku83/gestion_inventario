"""Única fuente de verdad para stock y deudas.

Stock = SUM(Movimiento IN no anulada) - SUM(Venta no anulada).
Deuda = total - pagado > 0 AND anulada=False (ignora a_plazos para la bandeja;
a_plazos queda solo como etiqueta Contado/A plazos).
"""
from collections import Counter
from decimal import Decimal

from django.db.models import F, Sum, Value, DecimalField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from movimiento.models import Movimiento, Venta, PagoVenta


def get_stock_map(product_ids=None):
    """dict producto_id -> stock disponible (int)."""
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


def get_stock(producto_id):
    return get_stock_map([producto_id]).get(producto_id, 0)


def get_deuda(venta):
    total = (venta.precio_unitario or Decimal("0.00")) * (venta.cantidad or 0)
    pagado = (
        PagoVenta.objects.filter(venta=venta).aggregate(
            s=Coalesce(Sum("monto"), Value(Decimal("0.00")))
        )["s"]
        or Decimal("0.00")
    )
    d = total - pagado
    return d if d > 0 else Decimal("0.00")


def ventas_con_deuda_qs():
    """Ventas no anuladas con deuda > 0, anotadas (sin N+1)."""
    pagos_sub = (
        PagoVenta.objects.filter(venta=OuterRef("pk"))
        .values("venta")
        .annotate(s=Sum("monto"))
        .values("s")
    )
    return (
        Venta.objects.filter(anulada=False)
        .select_related("producto", "producto__proveedor")
        .annotate(
            total_calc=F("precio_unitario") * F("cantidad"),
            pagado_calc=Coalesce(
                Subquery(pagos_sub, output_field=DecimalField(max_digits=18, decimal_places=2)),
                Value(Decimal("0.00")),
            ),
        )
        .annotate(deuda_calc=F("total_calc") - F("pagado_calc"))
        .filter(deuda_calc__gt=0)
        .order_by("-fecha")
    )


def validar_stock_lote(items):
    """items: iterable de (producto_id, cantidad). Retorna dict pid -> {'disponible', 'pedido'} solo con faltantes."""
    demand = Counter()
    for pid, qty in items:
        demand[pid] += qty or 0
    if not demand:
        return {}
    stock = get_stock_map(list(demand.keys()))
    faltantes = {}
    for pid, pedido in demand.items():
        disp = stock.get(pid, 0)
        if pedido > disp:
            faltantes[pid] = {"disponible": disp, "pedido": pedido}
    return faltantes
