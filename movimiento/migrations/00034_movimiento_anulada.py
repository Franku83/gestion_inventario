# movimiento/migrations/0003_movimiento_anulada.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("movimiento", "0002_alter_movimiento_tipo_venta_pagoventa"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimiento",
            name="anulada",
            field=models.BooleanField(default=False),
        ),
    ]
