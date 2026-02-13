from django.contrib import admin
from .models import Producto

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "proveedor", "tipo", "costo_unitario", "precio_venta_unitario", "activo")
    list_filter = ("proveedor", "tipo", "activo")
    search_fields = ("nombre", "sku")
