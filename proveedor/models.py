from django.db import models

class Proveedor(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    telefono = models.CharField(max_length=30, blank=True)
    nota = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
