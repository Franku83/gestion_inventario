import requests
import logging
from decimal import Decimal
from django.core.cache import cache
from django.db.models import Sum, Count
from producto.models import Producto
from proveedor.models import Proveedor
from movimiento.models import Movimiento, Venta

logger = logging.getLogger(__name__)

DOLAR_API_URL = "https://ve.dolarapi.com/v1/dolares"


def obtener_estadisticas_inventario():
    total_productos = Producto.objects.count()
    compras = Movimiento.objects.filter(tipo="IN", anulada=False).values("producto_id").annotate(total_in=Sum("cantidad"))
    ventas = Venta.objects.filter(anulada=False).values("producto_id").annotate(total_out=Sum("cantidad"))
    compras_map = {c["producto_id"]: c["total_in"] for c in compras}
    ventas_map = {v["producto_id"]: v["total_out"] for v in ventas}
    valor_total = Decimal("0.00")
    for p in Producto.objects.only("id", "costo_unitario"):
        qty = (compras_map.get(p.id, 0) or 0) - (ventas_map.get(p.id, 0) or 0)
        if qty > 0:
            valor_total += Decimal(qty) * (p.costo_unitario or Decimal("0.00"))
    proveedor_top = Proveedor.objects.annotate(num_prod=Count("productos")).order_by("-num_prod").first()
    return {
        "total_productos": total_productos,
        "valor_stock_usd": float(valor_total),
        "proveedor_con_mas_articulos": proveedor_top.nombre if proveedor_top else "Ninguno"
    }


def obtener_usd_bs_rate():
    cache_key = "usd_bs_rate"
    rate = cache.get(cache_key)
    if rate is not None:
        try:
            return Decimal(str(rate))
        except Exception:
            pass

    try:
        response = requests.get(DOLAR_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        for item in data:
            if item.get("fuente") == "oficial":
                promedio = item.get("promedio")
                if promedio is not None:
                    rate = Decimal(str(promedio))
                    cache.set(cache_key, str(rate), 60 * 30)
                    return rate
    except requests.RequestException as e:
        logger.warning("obtener_usd_bs_rate request failed: %s", e)
    except Exception as e:
        logger.warning("obtener_usd_bs_rate unexpected: %s", e)

    return Decimal("0.00")
