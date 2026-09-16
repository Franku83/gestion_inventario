"""Sprint 0: versión TestCase del flujo deudas (reemplaza test_all_deudas.py manual)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from movimiento.models import Movimiento, PagoVenta, Venta
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


class DeudasFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        prov = Proveedor.objects.create(nombre="Test Proveedor")
        tipo = TipoJoya.objects.create(nombre="Test Tipo")
        self.prod = Producto.objects.create(
            nombre="Test Producto", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=10, precio_unitario=Decimal("50.00"))

    def test_flujo_deuda_completo(self):
        # 1. deudas lista OK
        self.assertEqual(self.client.get(reverse("deudas_list")).status_code, 200)
        # 2. crear venta a plazos con pago inicial
        r = self.client.post(reverse("venta_create"), data={
            "cliente": "Cliente Test Deuda",
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "producto": self.prod.id, "cantidad": 2,
            "precio_unitario": Decimal("120.00"), "a_plazos": True,
            "nota": "Nota prueba", "pago_inicial": Decimal("40.00"),
        })
        self.assertIn(r.status_code, (302, 200))
        venta = Venta.objects.get(cliente="Cliente Test Deuda")
        self.assertEqual(venta.total, Decimal("240.00"))
        # 3. aparece en deudas
        self.assertContains(self.client.get(reverse("deudas_list")), "Cliente Test Deuda")
        # 4. detalle OK
        self.assertEqual(self.client.get(reverse("venta_detalle", args=[venta.id])).status_code, 200)
        # 5. abono
        r = self.client.post(reverse("pago_create", args=[venta.id]), data={
            "monto": Decimal("50.00"),
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "nota": "Abono parcial",
        })
        self.assertIn(r.status_code, (302, 200))
        venta.refresh_from_db()
        self.assertEqual(venta.pagado, Decimal("90.00"))
        # 6. editar venta
        r = self.client.post(reverse("venta_update", args=[venta.id]), data={
            "cliente": "Cliente Test Editado",
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "producto": self.prod.id, "cantidad": 3,
            "precio_unitario": Decimal("120.00"), "a_plazos": True, "nota": "editada",
        })
        self.assertIn(r.status_code, (302, 200))
        venta.refresh_from_db()
        self.assertEqual(venta.cliente, "Cliente Test Editado")
        self.assertEqual(venta.total, Decimal("360.00"))
        # 7. borrar pago
        pago = PagoVenta.objects.get(venta=venta, nota="Abono parcial")
        r = self.client.post(reverse("pago_delete", args=[pago.id]))
        self.assertIn(r.status_code, (302, 200))
        venta.refresh_from_db()
        self.assertEqual(venta.pagado, Decimal("40.00"))
