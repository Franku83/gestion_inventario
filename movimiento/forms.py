from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal

from movimiento.models import Movimiento, Venta, PagoVenta
from movimiento.services import get_stock_map
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


def _bootstrapify(form: forms.Form):
    """Pone clases Bootstrap automáticamente."""
    for name, field in form.fields.items():
        cls = field.widget.attrs.get("class", "")
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Select, forms.Textarea)):
            field.widget.attrs["class"] = (cls + " form-control").strip()
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = (cls + " form-check-input").strip()
    return form


class CompraForm(forms.ModelForm):
    """Formulario único de compra (crear/corregir una línea). Sprint 2."""

    class Meta:
        model = Movimiento
        fields = ["producto", "cantidad", "precio_unitario", "nota"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean_precio_unitario(self):
        p = self.cleaned_data.get("precio_unitario")
        if p is None:
            return Decimal("0.00")
        if p < 0:
            raise ValidationError("El precio no puede ser negativo.")
        return p


CompraEditForm = CompraForm  # compat Sprint 1


class VentaForm(forms.ModelForm):
    pago_inicial = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=Decimal("0.00"))

    class Meta:
        model = Venta
        fields = ["cliente", "producto", "cantidad", "precio_unitario", "a_plazos", "fecha", "nota"]
        widgets = {
            'fecha': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
        if not self.instance.pk:
            # Poner la hora local actual con formato adecuado para datetime-local
            self.initial['fecha'] = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')

    def clean_precio_unitario(self):
        p = self.cleaned_data.get("precio_unitario")
        if p is None:
            return Decimal("0.00")
        if p < 0:
            raise ValidationError("El precio no puede ser negativo.")
        return p

    def clean_pago_inicial(self):
        p = self.cleaned_data.get("pago_inicial")
        if p is None:
            return Decimal("0.00")
        if p < 0:
            raise ValidationError("El pago no puede ser negativo.")
        return p

    def clean(self):
        cleaned = super().clean()
        producto = cleaned.get("producto")
        cantidad = cleaned.get("cantidad")

        if producto and cantidad:
            stock = get_stock_map([producto.id]).get(producto.id, 0)
            if cantidad > stock:
                raise ValidationError(f"Stock insuficiente. Disponible: {stock}")
        return cleaned


class VentaEditForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ["cliente", "producto", "cantidad", "precio_unitario", "a_plazos", "fecha", "nota"]
        widgets = {
            'fecha': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean_precio_unitario(self):
        p = self.cleaned_data.get("precio_unitario")
        if p is None:
            return Decimal("0.00")
        if p < 0:
            raise ValidationError("El precio no puede ser negativo.")
        return p

    def clean(self):
        cleaned = super().clean()
        producto = cleaned.get("producto")
        cantidad = cleaned.get("cantidad")

        if producto and cantidad:
            stock = get_stock_map([producto.id]).get(producto.id, 0)
            # Si estamos editando y no cambió de producto, la cantidad actual no cuenta como salida.
            if self.instance.pk and self.instance.producto_id == producto.id and not self.instance.anulada:
                stock += self.instance.cantidad
            if cantidad > stock:
                raise ValidationError(f"Stock insuficiente. Disponible: {stock}")
        return cleaned


class PagoVentaForm(forms.ModelForm):
    class Meta:
        model = PagoVenta
        fields = ["monto", "fecha", "nota"]
        widgets = {
            'fecha': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local', 'class': 'form-control'}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
        if not self.instance.pk:
            self.initial['fecha'] = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')

    def clean_monto(self):
        m = self.cleaned_data.get("monto")
        if m is None:
            raise ValidationError("Monto requerido.")
        if m <= 0:
            raise ValidationError("El monto debe ser mayor que 0.")
        return m


class ItemCompraForm(forms.Form):
    crear_nuevo = forms.CharField(required=False, widget=forms.HiddenInput())

    # Producto existente
    producto = forms.ModelChoiceField(
        queryset=Producto.objects.filter(activo=True).order_by("nombre"),
        label="Producto existente",
        required=False,
    )

    # Nuevo producto
    nombre = forms.CharField(required=False, max_length=140, label="Nombre")
    proveedor = forms.ModelChoiceField(
        queryset=Proveedor.objects.all().order_by("nombre"),
        required=False, label="Proveedor",
    )
    tipo = forms.ModelChoiceField(
        queryset=TipoJoya.objects.all().order_by("nombre"),
        required=False, label="Tipo",
    )
    costo_unitario = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2,
        initial=Decimal("0.00"), label="Costo unitario",
    )
    precio_venta_unitario = forms.DecimalField(
        required=False, max_digits=12, decimal_places=2,
        initial=Decimal("0.00"), label="Precio venta",
    )

    # Compra
    cantidad = forms.IntegerField(min_value=1, initial=1, label="Cantidad")
    precio_unitario = forms.DecimalField(max_digits=12, decimal_places=2, initial=Decimal("0.00"), label="Precio compra")
    nota = forms.CharField(required=False, max_length=255, label="Nota")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean(self):
        cleaned = super().clean()
        crear = (cleaned.get("crear_nuevo") or "").lower() == "true"
        if crear:
            if not cleaned.get("nombre"):
                self.add_error("nombre", "Requerido.")
            if not cleaned.get("proveedor"):
                self.add_error("proveedor", "Requerido.")
            if not cleaned.get("tipo"):
                self.add_error("tipo", "Requerido.")
        else:
            if not cleaned.get("producto"):
                self.add_error("producto", "Selecciona un producto.")
        return cleaned

# Sprint 2: CompraUnificadaForm eliminado — el formset (ItemCompraForm) ya cubre
# producto existente + creación inline. Flujo único: compra_create.
CompraFormSet = forms.formset_factory(ItemCompraForm, extra=1, can_delete=True)
CompraMultipleFormSet = CompraFormSet  # compat Sprint 1


class ItemVentaForm(forms.Form):
    producto = forms.ModelChoiceField(
        queryset=Producto.objects.filter(activo=True).order_by("nombre"),
        label="Producto",
    )
    cantidad = forms.IntegerField(min_value=1, initial=1, label="Cantidad")
    precio_unitario = forms.DecimalField(
        max_digits=12, decimal_places=2, initial=Decimal("0.00"), label="Precio venta"
    )
    cliente = forms.CharField(required=False, max_length=150, label="Cliente")
    nota = forms.CharField(required=False, max_length=255, label="Nota")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean(self):
        cleaned = super().clean()
        producto = cleaned.get("producto")
        cantidad = cleaned.get("cantidad")
        if producto and cantidad:
            stock = get_stock_map([producto.id]).get(producto.id, 0)
            if cantidad > stock:
                self.add_error("cantidad", f"Stock insuficiente. Disponible: {stock}")
        return cleaned


VentaLoteFormSet = forms.formset_factory(ItemVentaForm, extra=1, can_delete=True)
