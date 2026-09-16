from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventario, name="inventario"),
    path("", include("proveedor.urls")),
    path("", include("tipologia.urls")),

    # compra
    path("compra/", views.compra_list, name="compra_list"),
    path("compra/registrar/", views.compra_create, name="compra_create"),
    path("compra/registrar-multiple/", views.compra_multiple, name="compra_multiple"),
    path("compra/<int:pk>/editar/", views.compra_update, name="compra_update"),
    path("compra/<int:pk>/eliminar/", views.compra_delete, name="compra_delete"),
    path("compra/<int:pk>/anular/", views.compra_anular, name="compra_anular"),

    # ventas / deudas / pagos (Sprint 1: tipos vive en tipologia/urls.py)
    path("venta/registrar/", views.venta_create, name="venta_create"),
    path("venta/registrar-lote/", views.venta_lote, name="venta_lote"),
    path("venta/<int:pk>/editar/", views.venta_update, name="venta_update"),
    path("deudas/", views.deudas_list, name="deudas_list"),
    path("venta/<int:pk>/", views.venta_detalle, name="venta_detalle"),
    path("venta/<int:pk>/anular/", views.venta_anular, name="venta_anular"),
    path("venta/<int:venta_id>/pago/", views.pago_create, name="pago_create"),
    path("pago/<int:pk>/eliminar/", views.pago_delete, name="pago_delete"),

    # resumen
    path("resumen-mensual/", views.resumen_mensual, name="resumen_mensual"),
]
