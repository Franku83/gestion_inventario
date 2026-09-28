from django.urls import path
from producto import views

urlpatterns = [
    path("productos/", views.producto_list, name="producto_list"),
    path("productos/crear/", views.producto_create, name="producto_create"),
    path("productos/<int:pk>/editar/", views.producto_update, name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.producto_delete, name="producto_delete"),
    path("productos/<int:pk>/desactivar/", views.producto_desactivar, name="producto_desactivar"),
    path("productos/<int:pk>/reactivar/", views.producto_reactivar, name="producto_reactivar"),
]
