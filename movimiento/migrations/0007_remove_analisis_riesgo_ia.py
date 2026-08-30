# Generated removal of IA field
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('movimiento', '0006_venta_anulada'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='venta',
            name='analisis_riesgo_ia',
        ),
    ]
