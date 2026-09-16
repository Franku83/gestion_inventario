from django.urls import path
from proveedor import views

urlpatterns = [
    path("proveedores/", views.proveedor_list, name="proveedor_list"),
    path("proveedores/crear/", views.proveedor_create, name="proveedor_create"),
    path("proveedores/<int:pk>/editar/", views.proveedor_update, name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.proveedor_delete, name="proveedor_delete"),
]
