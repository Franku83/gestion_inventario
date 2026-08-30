from django.db import models

class Producto(models.Model):
    nombre = models.CharField(max_length=140)

    proveedor = models.ForeignKey(
        'proveedor.Proveedor',
        on_delete=models.PROTECT,
        related_name='productos'
    )
    tipo = models.ForeignKey(
        'tipologia.TipoJoya',
        on_delete=models.PROTECT,
        related_name='productos'
    )

    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_venta_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["nombre", "proveedor", "tipo"], name="uniq_producto_por_proveedor_tipo")
        ]

    def __str__(self):
        return f"{self.nombre} ({self.proveedor})"
