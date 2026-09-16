"""Sprint 0: red de seguridad para el cálculo de stock (fuente: movimiento.services)."""
from decimal import Decimal

from django.test import TestCase

from movimiento.models import Movimiento, Venta
from movimiento.services import get_stock, get_stock_map, validar_stock_lote
from producto.models import Producto
from proveedor.models import Proveedor
from tipologia.models import TipoJoya


class StockServiceTests(TestCase):
    def setUp(self):
        prov = Proveedor.objects.create(nombre="Prov S")
        tipo = TipoJoya.objects.create(nombre="Tipo S")
        self.prod = Producto.objects.create(
            nombre="Anillo S", proveedor=prov, tipo=tipo,
            costo_unitario=Decimal("50.00"), precio_venta_unitario=Decimal("100.00"), activo=True,
        )
        Movimiento.objects.create(tipo="IN", producto=self.prod, cantidad=10, precio_unitario=Decimal("50.00"))

    def test_stock_basico(self):
        self.assertEqual(get_stock(self.prod.id), 10)
        Venta.objects.create(producto=self.prod, cantidad=3, precio_unitario=Decimal("120.00"))
        self.assertEqual(get_stock(self.prod.id), 7)
        self.assertEqual(get_stock_map([self.prod.id])[self.prod.id], 7)

    def test_anulada_devuelve_stock(self):
        v = Venta.objects.create(producto=self.prod, cantidad=3, precio_unitario=Decimal("120.00"))
        self.assertEqual(get_stock(self.prod.id), 7)
        v.anulada = True
        v.save()
        self.assertEqual(get_stock(self.prod.id), 10)

    def test_lote_no_permite_oversell_acumulado(self):
        falt = validar_stock_lote([(self.prod.id, 6), (self.prod.id, 5)])
        self.assertIn(self.prod.id, falt)
        self.assertEqual(falt[self.prod.id], {"disponible": 10, "pedido": 11})
        ok = validar_stock_lote([(self.prod.id, 6), (self.prod.id, 4)])
        self.assertEqual(ok, {})
