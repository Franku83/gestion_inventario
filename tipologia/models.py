from django.db import models

class TipoJoya(models.Model):
    nombre = models.CharField(max_length=80, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tipo de joya"
        verbose_name_plural = "Tipos de joya"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
