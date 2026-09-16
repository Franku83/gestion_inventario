"""Compat: la lógica vive en views_compras.py / views_ventas.py (Sprint 1)."""
from movimiento.views_compras import (  # noqa: F401
    compra_anular,
    compra_create,
    compra_delete,
    compra_list,
    compra_multiple,
    compra_update,
)
from movimiento.views_ventas import (  # noqa: F401
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
