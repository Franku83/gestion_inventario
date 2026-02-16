from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventario, name="inventario"),

    # compra
    path("compra/", views.compra_list, name="compra_list"),
    path("compra/registrar/", views.compra_create, name="compra_create"),
    path("compra/<int:pk>/editar/", views.compra_update, name="compra_update"),
    path("compra/<int:pk>/eliminar/", views.compra_delete, name="compra_delete"),
    path("compra/<int:pk>/anular/", views.compra_anular, name="compra_anular"),

    # proveedores
    path("proveedores/", views.proveedor_list, name="proveedor_list"),
    path("proveedores/crear/", views.proveedor_create, name="proveedor_create"),
    path("proveedores/<int:pk>/editar/", views.proveedor_update, name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.proveedor_delete, name="proveedor_delete"),

    # tipos
    path("tipos/", views.tipo_list, name="tipo_list"),
    path("tipos/crear/", views.tipo_create, name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("tipos/<int:pk>/eliminar/", views.tipo_delete, name="tipo_delete"),

    # ventas / deudas / pagos
    path("venta/registrar/", views.venta_create, name="venta_create"),
    path("deudas/", views.deudas_list, name="deudas_list"),
    path("venta/<int:pk>/", views.venta_detalle, name="venta_detalle"),
    path("venta/<int:venta_id>/pago/", views.pago_create, name="pago_create"),
    path("pago/<int:pk>/eliminar/", views.pago_delete, name="pago_delete"),
]
