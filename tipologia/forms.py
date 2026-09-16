from django import forms
from tipologia.models import TipoJoya


def _bootstrapify(form: forms.Form):
    for name, field in form.fields.items():
        cls = field.widget.attrs.get("class", "")
        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Select, forms.Textarea)):
            field.widget.attrs["class"] = (cls + " form-control").strip()
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = (cls + " form-check-input").strip()
    return form


class TipoJoyaForm(forms.ModelForm):
    class Meta:
        model = TipoJoya
        fields = ["nombre"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrapify(self)
