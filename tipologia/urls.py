from django.urls import path
from tipologia import views

urlpatterns = [
    path("tipos/", views.tipo_list, name="tipo_list"),
    path("tipos/crear/", views.tipo_create, name="tipo_create"),
    path("tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("tipos/<int:pk>/eliminar/", views.tipo_delete, name="tipo_delete"),
]
