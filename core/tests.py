from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Movimiento, Venta, PagoVenta
from core.forms import VentaForm, VentaEditForm

class VentaAnuladaTests(TestCase):
    def setUp(self):
        # Create user and log in
        self.user = User.objects.create_superuser(username="admin", password="password123")
        self.client = Client()
        self.client.login(username="admin", password="password123")

        # Create basic relationships
        self.proveedor = Proveedor.objects.create(nombre="Proveedor Test")
        self.tipo_joya = TipoJoya.objects.create(nombre="Tipo Test")
        
        # Create product
        self.producto = Producto.objects.create(
            nombre="Joyas de Oro",
            proveedor=self.proveedor,
            tipo=self.tipo_joya,
            costo_unitario=Decimal("50.00"),
            precio_venta_unitario=Decimal("100.00"),
            activo=True
        )

        # Create initial stock (IN movement)
        self.movimiento_stock = Movimiento.objects.create(
            tipo="IN",
            producto=self.producto,
            cantidad=10,
            precio_unitario=Decimal("50.00"),
            nota="Stock inicial"
        )

    def test_venta_anular_view_and_effects(self):
        # 1. Create a sale
        venta = Venta.objects.create(
            cliente="Cliente Test",
            producto=self.producto,
            cantidad=3,
            precio_unitario=Decimal("120.00"),
            a_plazos=True,
            fecha=timezone.now(),
            nota="Venta a plazos"
        )
        
        # Add a payment
        PagoVenta.objects.create(
            venta=venta,
            monto=Decimal("50.00"),
            fecha=timezone.now(),
            nota="Pago inicial"
        )

        # Confirm stock calculations, profit, and dashboard stats before annulling
        # Stock: 10 in - 3 out = 7 remaining
        response = self.client.get(reverse("inventario"))
        # Compat con paginación: productos es Page, buscar en object_list o iterar
        productos_ctx = response.context["productos"]
        try:
            prod_obj = productos_ctx.get(id=self.producto.id)
        except AttributeError:
            # Page object -> usar object_list QuerySet
            prod_obj = next((p for p in productos_ctx if p.id == self.producto.id), None)
            if prod_obj is None and hasattr(productos_ctx, "object_list"):
                prod_obj = productos_ctx.object_list.get(id=self.producto.id)
        self.assertIsNotNone(prod_obj)
        self.assertEqual(prod_obj.stock, 7)

        # Profit: (120 - 50) * 3 = 210 USD
        # Sold: 3 * 120 = 360 USD
        # Debt: 360 - 50 = 310 USD
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["dinero_vendido_usd"], Decimal("360.00"))
        self.assertEqual(response.context["dinero_deuda_usd"], Decimal("310.00"))
        self.assertEqual(response.context["ganancia_usd"], Decimal("210.00"))

        # Verify it appears in deudas list
        response = self.client.get(reverse("deudas_list"))
        self.assertContains(response, "Cliente Test")

        # 2. Annul the sale
        response = self.client.post(reverse("venta_anular", args=[venta.id]))
        self.assertRedirects(response, reverse("venta_detalle", args=[venta.id]))

        # Refresh from db
        venta.refresh_from_db()
        self.assertTrue(venta.anulada)

        # 3. Confirm stock calculations, profit, and dashboard stats after annulling
        # Stock should return to 10
        response = self.client.get(reverse("inventario"))
        productos_ctx = response.context["productos"]
        try:
            prod_obj = productos_ctx.get(id=self.producto.id)
        except AttributeError:
            prod_obj = next((p for p in productos_ctx if p.id == self.producto.id), None)
            if prod_obj is None and hasattr(productos_ctx, "object_list"):
                prod_obj = productos_ctx.object_list.get(id=self.producto.id)
        self.assertIsNotNone(prod_obj)
        self.assertEqual(prod_obj.stock, 10)

        # Profit, Sold, Debt should exclude the annulled sale (equal to 0 now)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["dinero_vendido_usd"], Decimal("0.00"))
        self.assertEqual(response.context["dinero_deuda_usd"], Decimal("0.00"))
        self.assertEqual(response.context["ganancia_usd"], Decimal("0.00"))

        # Verify it is excluded from deudas list
        response = self.client.get(reverse("deudas_list"))
        self.assertNotContains(response, "Cliente Test")

    def test_form_validation_respects_annulment(self):
        # Create a sale that consumes all stock (10)
        venta = Venta.objects.create(
            cliente="Cliente Stock Limit",
            producto=self.producto,
            cantidad=10,
            precio_unitario=Decimal("100.00"),
            a_plazos=False
        )

        # Try to register another sale (stock is 0, should fail validation)
        form_data = {
            "cliente": "Cliente Nuevo",
            "producto": self.producto.id,
            "cantidad": 1,
            "precio_unitario": Decimal("100.00"),
            "a_plazos": False,
            "fecha": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "pago_inicial": Decimal("0.00")
        }
        form = VentaForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("Stock insuficiente", form.errors["__all__"][0])

        # Annul the stock-consuming sale
        venta.anulada = True
        venta.save()

        # Try to register the same sale again (stock is now 10 again, should be valid)
        form = VentaForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_anular_redirects_to_referrer(self):
        venta = Venta.objects.create(
            cliente="Cliente Referrer Test",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("100.00"),
            a_plazos=True
        )
        
        # Test redirecting to referrer if HTTP_REFERER is set
        referrer_url = reverse("deudas_list")
        response = self.client.post(
            reverse("venta_anular", args=[venta.id]),
            HTTP_REFERER=referrer_url
        )
        self.assertRedirects(response, referrer_url)
        
        venta.refresh_from_db()
        self.assertTrue(venta.anulada)
