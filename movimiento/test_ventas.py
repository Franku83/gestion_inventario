"""Sprint 3: flujo único de ventas (formset + a_plazos por fila + pago inicial 1 fila)."""
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch
from django.utils import timezone

from movimiento.models import Movimiento, PagoVenta, Venta
from movimiento.services import get_stock
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


def formset_data(rows, pago_inicial="0.00", token=None):
    data = {
        "form-TOTAL_FORMS": str(len(rows)),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "idempotency_token": token or str(uuid.uuid4()),
        "pago_inicial": pago_inicial,
    }
    for i, r in enumerate(rows):
        p = f"form-{i}-"
        data[p + "producto"] = str(r.get("producto", ""))
        data[p + "cantidad"] = str(r.get("cantidad", "1"))
        data[p + "precio_unitario"] = str(r.get("precio_unitario", "0.00"))
        data[p + "cliente"] = r.get("cliente", "")
        if r.get("a_plazos"):
            data[p + "a_plazos"] = "on"
        data[p + "fecha"] = r.get("fecha", timezone.now().strftime("%Y-%m-%dT%H:%M"))
        data[p + "nota"] = r.get("nota", "")
    return data


class VentaUnicaTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        prov = Proveedor.objects.create(nombre="Prov V")
        tipo = TipoJoya.objects.create(nombre="Tipo V")
        self.prod = Producto.objects.create(
            nombre="Anillo V", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        self.prod2 = Producto.objects.create(
            nombre="Cadena V", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("20.00"), precio_venta_unitario=Decimal("40.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=10, precio_unitario=Decimal("50.00"))
        Movimiento.objects.create(tipo="IN", producto=self.prod2, cantidad=10, precio_unitario=Decimal("20.00"))

    def test_venta_unica_con_pago_inicial(self):
        r = self.client.post(reverse("venta_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 2, "precio_unitario": "120.00",
             "cliente": "Cliente 1", "a_plazos": True},
        ], pago_inicial="40.00"))
        self.assertEqual(r.status_code, 302)
        v = Venta.objects.get(cliente="Cliente 1")
        self.assertEqual(v.total, Decimal("240.00"))
        self.assertTrue(v.a_plazos)
        self.assertEqual(v.pagado, Decimal("40.00"))
        self.assertEqual(get_stock(self.prod.id), 8)

    def test_venta_multiples_filas_con_modalidad_por_fila(self):
        r = self.client.post(reverse("venta_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 1, "precio_unitario": "120.00",
             "cliente": "A", "a_plazos": True},
            {"producto": self.prod2.id, "cantidad": 2, "precio_unitario": "40.00", "cliente": "B"},
        ]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Venta.objects.count(), 2)
        self.assertTrue(Venta.objects.get(cliente="A").a_plazos)
        self.assertFalse(Venta.objects.get(cliente="B").a_plazos)

    def test_pago_inicial_rechazado_con_varias_filas(self):
        r = self.client.post(reverse("venta_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 1, "precio_unitario": "120.00"},
            {"producto": self.prod2.id, "cantidad": 1, "precio_unitario": "40.00"},
        ], pago_inicial="10.00"))
        self.assertEqual(r.status_code, 200)  # re-render con error
        self.assertContains(r, "pago inicial")
        self.assertEqual(Venta.objects.count(), 0)

    def test_stock_insuficiente_acumulado_en_lote(self):
        r = self.client.post(reverse("venta_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 6, "precio_unitario": "120.00"},
            {"producto": self.prod.id, "cantidad": 5, "precio_unitario": "120.00"},
        ]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Stock insuficiente")
        self.assertEqual(Venta.objects.count(), 0)

    def test_url_vieja_lote_redirige(self):
        r = self.client.get("/venta/registrar-lote/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.endswith("/venta/registrar/"))
        with self.assertRaises(NoReverseMatch):
            reverse("venta_lote", args=[])

    def test_pago_bloquea_sobrepago(self):
        v = Venta.objects.create(producto=self.prod, cantidad=2, precio_unitario=Decimal("120.00"), a_plazos=True)
        r = self.client.post(reverse("pago_create", args=[v.id]), data={
            "monto": Decimal("500.00"),
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        })
        self.assertEqual(r.status_code, 200)  # re-render con error, no guarda
        self.assertContains(r, "excede la deuda")
        self.assertEqual(PagoVenta.objects.filter(venta=v).count(), 0)

    def test_pago_vuelve_a_deudas_con_next(self):
        v = Venta.objects.create(producto=self.prod, cantidad=2, precio_unitario=Decimal("120.00"), a_plazos=True)
        url = reverse("pago_create", args=[v.id]) + "?next=/deudas/"
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, data={
            "monto": Decimal("50.00"),
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "next": "/deudas/",
        })
        self.assertRedirects(r, "/deudas/")
        v.refresh_from_db()
        self.assertEqual(v.pagado, Decimal("50.00"))

    def test_deuda_contado_tambien_aparece_en_bandeja(self):
        # Definición única Sprint 3: deuda>0 aunque sea contado
        Venta.objects.create(producto=self.prod, cantidad=1, precio_unitario=Decimal("100.00"), a_plazos=False)
        self.assertContains(self.client.get(reverse("deudas_list")), "$100")
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["dinero_deuda_usd"], Decimal("100.00"))
