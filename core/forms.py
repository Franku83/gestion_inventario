from django import forms
from decimal import Decimal
from django.core.exceptions import ValidationError

from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta


def _bootstrapify(form: forms.Form):
    """Pone clases Bootstrap automáticamente."""
    for name, field in form.fields.items():
        cls = field.widget.attrs.get("class", "")
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Select, forms.Textarea)):
            field.widget.attrs["class"] = (cls + " form-control").strip()
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = (cls + " form-check-input").strip()
    return form


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "telefono", "nota"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class TipoJoyaForm(forms.ModelForm):
    class Meta:
        model = TipoJoya
        fields = ["nombre"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "proveedor", "tipo", "costo_unitario", "precio_venta_unitario", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)


class CompraEditForm(forms.ModelForm):
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


class VentaForm(forms.ModelForm):
    pago_inicial = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=Decimal("0.00"))

    class Meta:
        model = Venta
        fields = ["producto", "cantidad", "precio_unitario", "a_plazos", "nota"]

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

    def clean_pago_inicial(self):
        p = self.cleaned_data.get("pago_inicial")
        if p is None:
            return Decimal("0.00")
        if p < 0:
            raise ValidationError("El pago no puede ser negativo.")
        return p


class PagoVentaForm(forms.ModelForm):
    class Meta:
        model = PagoVenta
        fields = ["monto", "nota"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)

    def clean_monto(self):
        m = self.cleaned_data.get("monto")
        if m is None:
            raise ValidationError("Monto requerido.")
        if m <= 0:
            raise ValidationError("El monto debe ser mayor que 0.")
        return m


class CompraUnificadaForm(forms.Form):
    crear_producto = forms.BooleanField(required=False, initial=False, label="Nuevo producto")

    producto_existente = forms.ModelChoiceField(
        queryset=Producto.objects.all().order_by("nombre"),
        required=False,
        label="Producto existente",
    )

    nombre = forms.CharField(required=False, max_length=140, label="Nombre del producto")
    proveedor = forms.ModelChoiceField(queryset=Proveedor.objects.all().order_by("nombre"), required=False)
    tipo = forms.ModelChoiceField(queryset=TipoJoya.objects.all().order_by("nombre"), required=False)
    costo_unitario = forms.DecimalField(required=False, max_digits=12, decimal_places=2, initial=Decimal("0.00"))
    precio_venta_unitario = forms.DecimalField(required=False, max_digits=12, decimal_places=2, initial=Decimal("0.00"))
    activo = forms.BooleanField(required=False, initial=True)

    cantidad = forms.IntegerField(min_value=1, label="Cantidad")
    precio_unitario = forms.DecimalField(max_digits=12, decimal_places=2, initial=Decimal("0.00"), label="Precio unitario (compra)")
    nota = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
        self.fields["nombre"].widget.attrs["placeholder"] = "Ej: Cadena corazón"
        self.fields["nota"].widget.attrs["placeholder"] = "Opcional"

    def clean(self):
        cleaned = super().clean()
        crear = cleaned.get("crear_producto")

        if crear:
            for f in ["nombre", "proveedor", "tipo"]:
                if not cleaned.get(f):
                    self.add_error(f, "Requerido para crear el producto.")
        else:
            if not cleaned.get("producto_existente"):
                self.add_error("producto_existente", "Selecciona un producto o marca 'Nuevo producto'.")

        pu = cleaned.get("precio_unitario")
        if pu is not None and pu < 0:
            self.add_error("precio_unitario", "No puede ser negativo.")

        return cleaned

    def save(self):
        data = self.cleaned_data

        if data["crear_producto"]:
            producto = Producto.objects.create(
                nombre=data["nombre"],
                proveedor=data["proveedor"],
                tipo=data["tipo"],
                costo_unitario=data.get("costo_unitario") or Decimal("0.00"),
                precio_venta_unitario=data.get("precio_venta_unitario") or Decimal("0.00"),
                activo=data.get("activo") is True,
            )
        else:
            producto = data["producto_existente"]

        mov = Movimiento.objects.create(
            tipo="IN",
            producto=producto,
            cantidad=data["cantidad"],
            precio_unitario=data.get("precio_unitario") or Decimal("0.00"),
            nota=data.get("nota") or "",
        )

        return producto, mov
