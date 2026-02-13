from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Movimiento(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "IN", "Entrada (Compra)"
        SALIDA = "OUT", "Salida (No usar)"  # lo dejamos por compatibilidad

    tipo = models.CharField(max_length=3, choices=Tipo.choices, default=Tipo.ENTRADA)

    producto = models.ForeignKey(
        'producto.Producto',
        on_delete=models.PROTECT,
        related_name='movimientos'
    )

    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    fecha = models.DateTimeField(auto_now_add=True)
    nota = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.producto} x{self.cantidad}"


class Venta(models.Model):
    producto = models.ForeignKey(
        'producto.Producto',
        on_delete=models.PROTECT,
        related_name='ventas'
    )

    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    a_plazos = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)
    nota = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-fecha"]

    @property
    def total(self):
        return (self.precio_unitario or Decimal("0.00")) * self.cantidad

    @property
    def pagado(self):
        # suma de pagos
        return sum((p.monto for p in self.pagos.all()), Decimal("0.00"))

    @property
    def deuda(self):
        d = self.total - self.pagado
        return d if d > 0 else Decimal("0.00")

    def __str__(self):
        return f"Venta - {self.producto} x{self.cantidad}"


class PagoVenta(models.Model):
    venta = models.ForeignKey(
        'movimiento.Venta',
        on_delete=models.CASCADE,
        related_name='pagos'
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateTimeField(auto_now_add=True)
    nota = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Pago {self.monto} - {self.venta}"
