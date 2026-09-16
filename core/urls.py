from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inventario/", views.inventario, name="inventario"),
    path("", include("proveedor.urls")),
    path("", include("tipologia.urls")),
    path("", include("movimiento.urls")),
]
