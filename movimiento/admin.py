from django.contrib import admin
from .models import Movimiento

@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "producto", "cantidad", "precio_unitario", "fecha")
    list_filter = ("tipo", "fecha")
    search_fields = ("producto__nombre",)
