"""Sprint 2: flujo único de compras (formset existente+nuevo, anular, sin borrado físico)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse, NoReverseMatch

from movimiento.models import Movimiento
from movimiento.services import get_stock
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


def formset_data(rows):
    data = {
        "form-TOTAL_FORMS": str(len(rows)),
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }
    for i, r in enumerate(rows):
        p = f"form-{i}-"
        data[p + "crear_nuevo"] = r.get("crear_nuevo", "false")
        data[p + "producto"] = str(r.get("producto", ""))
        data[p + "nombre"] = r.get("nombre", "")
        data[p + "proveedor"] = str(r.get("proveedor", ""))
        data[p + "tipo"] = str(r.get("tipo", ""))
        data[p + "costo_unitario"] = str(r.get("costo_unitario", "0.00"))
        data[p + "precio_venta_unitario"] = str(r.get("precio_venta_unitario", "0.00"))
        data[p + "cantidad"] = str(r.get("cantidad", "1"))
        data[p + "precio_unitario"] = str(r.get("precio_unitario", "0.00"))
        data[p + "nota"] = r.get("nota", "")
    return data


class CompraUnicaTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser(username="admin", password="password123")
        self.client.login(username="admin", password="password123")
        self.prov = Proveedor.objects.create(nombre="Prov C")
        self.tipo = TipoJoya.objects.create(nombre="Tipo C")
        self.prod = Producto.objects.create(
            nombre="Cadena C", proveedor=self.prov, tipo=self.tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )

    def test_registrar_compra_producto_existente(self):
        r = self.client.post(reverse("compra_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 5, "precio_unitario": "50.00"},
        ]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(get_stock(self.prod.id), 5)
        mov = Movimiento.objects.get(producto=self.prod)
        self.assertEqual(mov.cantidad, 5)

    def test_registrar_compra_creando_producto_inline(self):
        r = self.client.post(reverse("compra_create"), data=formset_data([
            {"crear_nuevo": "true", "nombre": "Anillo Nuevo", "proveedor": self.prov.id,
             "tipo": self.tipo.id, "costo_unitario": "30.00",
             "precio_venta_unitario": "80.00", "cantidad": 3, "precio_unitario": "30.00"},
        ]))
        self.assertEqual(r.status_code, 302)
        nuevo = Producto.objects.get(nombre="Anillo Nuevo")
        self.assertEqual(get_stock(nuevo.id), 3)

    def test_registrar_varias_filas_de_una_vez(self):
        r = self.client.post(reverse("compra_create"), data=formset_data([
            {"producto": self.prod.id, "cantidad": 2, "precio_unitario": "50.00"},
            {"crear_nuevo": "true", "nombre": "Dije Lote", "proveedor": self.prov.id,
             "tipo": self.tipo.id, "cantidad": 4, "precio_unitario": "10.00"},
        ]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(get_stock(self.prod.id), 2)
        self.assertEqual(get_stock(Producto.objects.get(nombre="Dije Lote").id), 4)

    def test_anular_excluye_del_stock(self):
        mov = Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=5, precio_unitario=Decimal("50.00"))
        self.assertEqual(get_stock(self.prod.id), 5)
        r = self.client.post(reverse("compra_anular", args=[mov.id]))
        self.assertEqual(r.status_code, 302)
        mov.refresh_from_db()
        self.assertTrue(mov.anulada)
        self.assertEqual(get_stock(self.prod.id), 0)
        self.assertNotContains(self.client.get(reverse("compra_list")), "Cadena C")

    def test_url_vieja_lote_redirige_al_flujo_unico(self):
        r = self.client.get("/compra/registrar-multiple/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.endswith("/compra/registrar/"))

    def test_borrado_fisico_eliminado(self):
        with self.assertRaises(NoReverseMatch):
            reverse("compra_delete", args=[1])
        mov = Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=1, precio_unitario=Decimal("1.00"))
        r = self.client.post(f"/compra/{mov.id}/eliminar/")
        self.assertEqual(r.status_code, 404)
