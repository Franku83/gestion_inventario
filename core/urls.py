from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventario, name="inventario"),

    # Compra
    path("compra/registrar/", views.compra_create, name="compra_create"),
    path("compra/", views.compra_list, name="compra_list"),
    path("compra/<int:pk>/editar/", views.compra_update, name="compra_update"),
    path("compra/<int:pk>/eliminar/", views.compra_delete, name="compra_delete"),


    # Venta + Deudas
    path("venta/registrar/", views.venta_create, name="venta_create"),
    path("venta/deudas/", views.deudas_list, name="deudas_list"),
    path("venta/<int:venta_id>/abonar/", views.abono_create, name="abono_create"),

    # Proveedores
    path("proveedores/", views.proveedor_list, name="proveedor_list"),
    path("proveedores/nuevo/", views.proveedor_create, name="proveedor_create"),
    path("proveedores/<int:pk>/editar/", views.proveedor_update, name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.proveedor_delete, name="proveedor_delete"),

    # Tipos
    path("tipos/", views.tipo_list, name="tipo_list"),
    path("tipos/nuevo/", views.tipo_create, name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("tipos/<int:pk>/eliminar/", views.tipo_delete, name="tipo_delete"),

    # Productos
    path("productos/", views.producto_list, name="producto_list"),
    path("productos/nuevo/", views.producto_create, name="producto_create"),
    path("productos/<int:pk>/editar/", views.producto_update, name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.producto_delete, name="producto_delete"),
]
