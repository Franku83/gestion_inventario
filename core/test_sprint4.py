"""Sprint 4: inventario accionable, prefill, dashboard útil, resumen ORM."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from movimiento.models import Movimiento, Venta
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


class Sprint4Tests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        prov = Proveedor.objects.create(nombre="Prov 4")
        tipo = TipoJoya.objects.create(nombre="Tipo 4")
        self.con_stock = Producto.objects.create(
            nombre="Con Stock", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        self.sin_stock = Producto.objects.create(
            nombre="Sin Stock", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("10.00"), precio_venta_unitario=Decimal("20.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.con_stock, cantidad=5, precio_unitario=Decimal("50.00"))

    def _nombres_inventario(self, response):
        page = response.context["productos"]
        try:
            qs = page.object_list
        except AttributeError:
            qs = page
        return {p.nombre for p in qs}

    def test_solo_stock_on_por_defecto(self):
        r = self.client.get(reverse("inventario"))
        nombres = self._nombres_inventario(r)
        self.assertIn("Con Stock", nombres)
        self.assertNotIn("Sin Stock", nombres)
        r = self.client.get(reverse("inventario") + "?solo_stock=off")
        self.assertIn("Sin Stock", self._nombres_inventario(r))

    def test_acciones_vender_comprar(self):
        r = self.client.get(reverse("inventario"))
        self.assertContains(r, f"/venta/registrar/?producto={self.con_stock.id}")
        self.assertContains(r, f"/compra/registrar/?producto={self.con_stock.id}")

    def test_prefill_venta_y_compra(self):
        r = self.client.get(reverse("venta_create") + f"?producto={self.con_stock.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["formset"].forms[0].initial.get("producto"), self.con_stock.id)
        r = self.client.get(reverse("compra_create") + f"?producto={self.con_stock.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["formset"].forms[0].initial.get("producto"), self.con_stock.id)
        # id inválido → sin prefill, sin error
        r = self.client.get(reverse("venta_create") + "?producto=999999")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["formset"].forms[0].initial.get("producto"))

    def test_dashboard_listas_accionables(self):
        Venta.objects.create(producto=self.con_stock, cantidad=1, precio_unitario=Decimal("120.00"),
                             cliente="Deudor 4", a_plazos=True)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Deudor 4")
        top = [v.cliente for v in r.context["top_deudas"]]
        self.assertIn("Deudor 4", top)

    def test_inmovilizado_solo_sin_ventas_90d(self):
        vieja = timezone.now() - timedelta(days=100)
        Venta.objects.create(producto=self.con_stock, cantidad=1, precio_unitario=Decimal("120.00"), fecha=vieja)
        # otro producto con venta reciente no debe salir
        prov = Proveedor.objects.first()
        tipo = TipoJoya.objects.first()
        rota = Producto.objects.create(nombre="Rota", proveedor=prov, tipo=tipo,
                                       costo_unitario=Decimal("5.00"), precio_venta_unitario=Decimal("10.00"), activo=True)
        Movimiento.objects.create(tipo="IN", producto=rota, cantidad=9, precio_unitario=Decimal("5.00"))
        Venta.objects.create(producto=rota, cantidad=1, precio_unitario=Decimal("10.00"))
        r = self.client.get(reverse("dashboard"))
        nombres = {x["producto"].nombre for x in r.context["top_inmovilizado"]}
        self.assertIn("Con Stock", nombres)
        self.assertNotIn("Rota", nombres)
        self.assertContains(r, "Stock inmovilizado")

    def test_resumen_mensual_orm(self):
        anio = timezone.now().year
        Movimiento.objects.create(tipo="IN", producto=self.con_stock, cantidad=100, precio_unitario=Decimal("50.00"))
        Venta.objects.create(producto=self.con_stock, cantidad=2, precio_unitario=Decimal("120.00"),
                             fecha=timezone.make_aware(datetime(anio, 1, 15, 12, 0)))
        Venta.objects.create(producto=self.con_stock, cantidad=1, precio_unitario=Decimal("100.00"),
                             fecha=timezone.make_aware(datetime(anio, 3, 20, 12, 0)))
        r = self.client.get(reverse("resumen_mensual") + f"?anio={anio}")
        self.assertEqual(r.status_code, 200)
        por_mes = {x["mes"]: x for x in r.context["resumen"]}
        self.assertEqual(por_mes[1]["num_ventas"], 1)
        self.assertAlmostEqual(por_mes[1]["total_vendido"], 240.0)
        self.assertAlmostEqual(por_mes[1]["total_costo"], 100.0)
        self.assertAlmostEqual(por_mes[1]["ganancia"], 140.0)
        self.assertEqual(por_mes[3]["num_ventas"], 1)
        self.assertAlmostEqual(r.context["total_general_vendido"], 340.0)
        self.assertAlmostEqual(r.context["total_general_ganancia"], 190.0)
