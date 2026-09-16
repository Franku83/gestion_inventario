from django.urls import path
from producto import views

# Nota: producto_list/create/update/delete no tienen rutas propias en core/urls
# (solo se usan vía inventario). Se exponen aquí para completar el desacople S1;
# el alta real de URLs se hará en Sprint 2 si se decide exponer CRUD producto.
urlpatterns = [
    path("productos/", views.producto_list, name="producto_list"),
    path("productos/crear/", views.producto_create, name="producto_create"),
    path("productos/<int:pk>/editar/", views.producto_update, name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.producto_delete, name="producto_delete"),
]
