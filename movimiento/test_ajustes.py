"""Bajas de stock (ADJ): restan stock sin tocar vendido/ganancia; reversibles vía anular."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from movimiento.models import Movimiento, Venta
from movimiento.services import get_stock
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


class AjusteBajaTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        prov = Proveedor.objects.create(nombre="Prov B")
        tipo = TipoJoya.objects.create(nombre="Tipo B")
        self.prod = Producto.objects.create(
            nombre="Anillo B", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=10, precio_unitario=Decimal("50.00"))

    def test_baja_resta_stock(self):
        r = self.client.post(reverse("ajuste_create", args=[self.prod.id]), data={
            "cantidad": 4, "motivo": "pieza dañada",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(get_stock(self.prod.id), 6)
        mov = Movimiento.objects.get(producto=self.prod, tipo="ADJ")
        self.assertEqual(mov.cantidad, 4)
        self.assertIn("BAJA", mov.nota)

    def test_baja_no_toca_vendido_ganancia(self):
        self.client.post(reverse("ajuste_create", args=[self.prod.id]), data={
            "cantidad": 4, "motivo": "pérdida",
        })
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["dinero_vendido_usd"], Decimal("0.00"))
        self.assertEqual(r.context["ganancia_usd"], Decimal("0.00"))
        # dinero en stock sí baja: 6 x 50 = 300
        self.assertEqual(r.context["dinero_stock_usd"], Decimal("300.00"))

    def test_baja_mayor_que_stock_falla(self):
        r = self.client.post(reverse("ajuste_create", args=[self.prod.id]), data={
            "cantidad": 99, "motivo": "error",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Solo hay 10 en stock")
        self.assertEqual(get_stock(self.prod.id), 10)
        self.assertFalse(Movimiento.objects.filter(tipo="ADJ").exists())

    def test_venta_respeta_baja(self):
        Movimiento.objects.create(tipo="ADJ", producto=self.prod, cantidad=7, precio_unitario=Decimal("0.00"), nota="BAJA: test")
        # stock = 3 → vender 5 debe fallar a nivel servicio
        from movimiento.services import validar_stock_lote
        falt = validar_stock_lote([(self.prod.id, 5)])
        self.assertIn(self.prod.id, falt)
        self.assertEqual(falt[self.prod.id]["disponible"], 3)

    def test_anular_baja_devuelve_stock(self):
        mov = Movimiento.objects.create(tipo="ADJ", producto=self.prod, cantidad=4, precio_unitario=Decimal("0.00"), nota="BAJA: test")
        self.assertEqual(get_stock(self.prod.id), 6)
        r = self.client.post(reverse("ajuste_anular", args=[mov.id]))
        self.assertEqual(r.status_code, 302)
        mov.refresh_from_db()
        self.assertTrue(mov.anulada)
        self.assertEqual(get_stock(self.prod.id), 10)

    def test_inventario_muestra_fechas_y_boton(self):
        Venta.objects.create(producto=self.prod, cantidad=1, precio_unitario=Decimal("100.00"))
        r = self.client.get(reverse("inventario"))
        self.assertEqual(r.status_code, 200)
        page = r.context["productos"]
        obj = next((p for p in page if p.id == self.prod.id), None)
        if obj is None and hasattr(page, "object_list"):
            obj = page.object_list.get(id=self.prod.id)
        self.assertIsNotNone(obj.ultimo_ingreso)
        self.assertIsNotNone(obj.ultima_venta)
        self.assertContains(r, reverse("ajuste_create", args=[self.prod.id]))
        # lista de bajas accesible
        self.assertEqual(self.client.get(reverse("ajuste_list")).status_code, 200)
