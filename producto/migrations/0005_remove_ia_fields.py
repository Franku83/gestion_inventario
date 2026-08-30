# Generated removal of IA fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('producto', '0004_producto_precio_sugerido_ia'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='producto',
            name='descripcion_ia',
        ),
        migrations.RemoveField(
            model_name='producto',
            name='precio_sugerido_ia',
        ),
    ]
