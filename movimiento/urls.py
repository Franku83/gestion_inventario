from django.urls import path
from django.views.generic import RedirectView
from movimiento import views_compras, views_ventas

urlpatterns = [
    # compras — flujo único Sprint 2 (una sola pantalla Registrar compra)
    path("compra/", views_compras.compra_list, name="compra_list"),
    path("compra/registrar/", views_compras.compra_create, name="compra_create"),
    # Compat: la vieja URL en lote redirige al flujo único
    path("compra/registrar-multiple/", RedirectView.as_view(pattern_name="compra_create", permanent=False)),
    path("compra/<int:pk>/editar/", views_compras.compra_update, name="compra_update"),
    # Sprint 2: eliminado compra_delete (borrado físico). Usar anular (reversible, conserva historial).
    path("compra/<int:pk>/anular/", views_compras.compra_anular, name="compra_anular"),

    # ventas / deudas / pagos — flujo único Sprint 3 (una sola pantalla Registrar venta)
    path("venta/registrar/", views_ventas.venta_create, name="venta_create"),
    # Compat: la vieja URL en lote redirige al flujo único
    path("venta/registrar-lote/", RedirectView.as_view(pattern_name="venta_create", permanent=False)),
    path("venta/<int:pk>/editar/", views_ventas.venta_update, name="venta_update"),
    path("deudas/", views_ventas.deudas_list, name="deudas_list"),
    path("venta/<int:pk>/", views_ventas.venta_detalle, name="venta_detalle"),
    path("venta/<int:pk>/anular/", views_ventas.venta_anular, name="venta_anular"),
    path("venta/<int:venta_id>/pago/", views_ventas.pago_create, name="pago_create"),
    path("pago/<int:pk>/eliminar/", views_ventas.pago_delete, name="pago_delete"),

    # resumen
    path("resumen-mensual/", views_ventas.resumen_mensual, name="resumen_mensual"),
]
