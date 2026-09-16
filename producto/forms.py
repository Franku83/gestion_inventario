from django import forms
from producto.models import Producto


def _bootstrapify(form: forms.Form):
    for name, field in form.fields.items():
        cls = field.widget.attrs.get("class", "")
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Select, forms.Textarea)):
            field.widget.attrs["class"] = (cls + " form-control").strip()
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = (cls + " form-check-input").strip()
    return form


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "proveedor", "tipo", "costo_unitario", "precio_venta_unitario", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
