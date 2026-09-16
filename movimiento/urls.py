from django.urls import path
from movimiento import views_compras, views_ventas

urlpatterns = [
    # compras
    path("compra/", views_compras.compra_list, name="compra_list"),
    path("compra/registrar/", views_compras.compra_create, name="compra_create"),
    path("compra/registrar-multiple/", views_compras.compra_multiple, name="compra_multiple"),
    path("compra/<int:pk>/editar/", views_compras.compra_update, name="compra_update"),
    path("compra/<int:pk>/eliminar/", views_compras.compra_delete, name="compra_delete"),
    path("compra/<int:pk>/anular/", views_compras.compra_anular, name="compra_anular"),

    # ventas / deudas / pagos
    path("venta/registrar/", views_ventas.venta_create, name="venta_create"),
    path("venta/registrar-lote/", views_ventas.venta_lote, name="venta_lote"),
    path("venta/<int:pk>/editar/", views_ventas.venta_update, name="venta_update"),
    path("deudas/", views_ventas.deudas_list, name="deudas_list"),
    path("venta/<int:pk>/", views_ventas.venta_detalle, name="venta_detalle"),
    path("venta/<int:pk>/anular/", views_ventas.venta_anular, name="venta_anular"),
    path("venta/<int:venta_id>/pago/", views_ventas.pago_create, name="pago_create"),
    path("pago/<int:pk>/eliminar/", views_ventas.pago_delete, name="pago_delete"),

    # resumen
    path("resumen-mensual/", views_ventas.resumen_mensual, name="resumen_mensual"),
]
