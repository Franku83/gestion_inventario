from django import forms


def _bootstrapify(form: forms.Form):
    """Pone clases Bootstrap automáticamente. (Histórico: cada app tiene su copia.)"""
    for name, field in form.fields.items():
        cls = field.widget.attrs.get("class", "")
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Select, forms.Textarea)):
            field.widget.attrs["class"] = (cls + " form-control").strip()
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = (cls + " form-check-input").strip()
    return form


# Sprint 1: fuente real en proveedor/forms.py. Re-export compat.
from proveedor.forms import ProveedorForm  # noqa: F401,E402


# Sprint 1: fuentes reales en tipologia/forms.py y producto/forms.py. Re-export compat.
from tipologia.forms import TipoJoyaForm  # noqa: F401,E402
from producto.forms import ProductoForm  # noqa: F401,E402


# Sprint 1-3: fuente real en movimiento/forms.py. Re-export compat.
# Sprint 3: VentaForm (single) eliminado; VentaLoteFormSet es alias. Flujo único = VentaFormSet.
from movimiento.forms import (  # noqa: F401,E402
    AjusteBajaForm,
    CompraEditForm,
    CompraForm,
    CompraFormSet,
    CompraMultipleFormSet,
    ItemCompraForm,
    ItemVentaForm,
    PagoVentaForm,
    VentaEditForm,
    VentaFormSet,
    VentaLoteFormSet,
)
