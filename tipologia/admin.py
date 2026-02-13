from django.contrib import admin
from .models import TipoJoya

@admin.register(TipoJoya)
class TipoJoyaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)

