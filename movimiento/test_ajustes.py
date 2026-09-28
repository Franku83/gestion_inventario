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

    def test_baja_motivo_largo_no_rompe_nota(self):
        # nota tiene max 255 (Postgres lo exige): motivo de 255 chars no debe fallar
        r = self.client.post(reverse("ajuste_create", args=[self.prod.id]), data={
            "cantidad": 2, "motivo": "x" * 255,
        })
        self.assertEqual(r.status_code, 302)
        mov = Movimiento.objects.get(producto=self.prod, tipo="ADJ")
        self.assertLessEqual(len(mov.nota), 255)
        self.assertEqual(get_stock(self.prod.id), 8)

    def test_baja_total_oculta_producto_del_inventario(self):
        self.client.post(reverse("ajuste_create", args=[self.prod.id]), data={
            "cantidad": 10, "motivo": "limpieza",
        })
        self.assertEqual(get_stock(self.prod.id), 0)
        r = self.client.get(reverse("inventario"))
        # con solo_stock=on (default) la tabla queda vacía (el nombre solo sale en el mensaje flash)
        self.assertContains(r, "No hay productos en inventario")

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

    def test_baja_sin_stock_ofrece_desactivar(self):
        # stock 0 → la página no muestra el form sino la opción de desactivar
        Movimiento.objects.filter(producto=self.prod, tipo="IN").update(anulada=True)
        self.assertEqual(get_stock(self.prod.id), 0)
        r = self.client.get(reverse("ajuste_create", args=[self.prod.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Desactivar producto")
        self.assertContains(r, reverse("producto_desactivar", args=[self.prod.id]))

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


class ProductoActivoTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        prov = Proveedor.objects.create(nombre="Prov D")
        tipo = TipoJoya.objects.create(nombre="Tipo D")
        self.prod = Producto.objects.create(
            nombre="Anillo D", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=5, precio_unitario=Decimal("50.00"))

    def _nombres_inventario(self, response):
        page = response.context["productos"]
        return {p.nombre for p in page}

    def test_desactivar_oculta_de_inventario(self):
        r = self.client.post(reverse("producto_desactivar", args=[self.prod.id]))
        self.assertEqual(r.status_code, 302)
        self.prod.refresh_from_db()
        self.assertFalse(self.prod.activo)
        self.assertNotIn("Anillo D", self._nombres_inventario(self.client.get(reverse("inventario"))))
        # opt-in la vuelve a mostrar con badge + reactivar
        r = self.client.get(reverse("inventario") + "?inactivos=on&solo_stock=off")
        self.assertIn("Anillo D", self._nombres_inventario(r))
        self.assertContains(r, "Desactivado")
        self.assertContains(r, reverse("producto_reactivar", args=[self.prod.id]))

    def test_reactivar_devuelve_a_inventario(self):
        self.prod.activo = False
        self.prod.save()
        r = self.client.post(reverse("producto_reactivar", args=[self.prod.id]))
        self.assertEqual(r.status_code, 302)
        self.prod.refresh_from_db()
        self.assertTrue(self.prod.activo)
        self.assertIn("Anillo D", self._nombres_inventario(self.client.get(reverse("inventario"))))

    def test_desactivar_desde_baja_vuelve_a_inventario(self):
        Movimiento.objects.filter(producto=self.prod, tipo="IN").update(anulada=True)
        r = self.client.post(
            reverse("producto_desactivar", args=[self.prod.id]) + "?next=" + reverse("inventario")
        )
        self.assertRedirects(r, reverse("inventario"))

    def test_producto_list_muestra_estado_y_acciones(self):
        self.prod.activo = False
        self.prod.save()
        r = self.client.get(reverse("producto_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Desactivado")
        self.assertContains(r, reverse("producto_reactivar", args=[self.prod.id]))
