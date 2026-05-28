import os
import sys
import django
from decimal import Decimal

# Set up Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "joyerias_inventario.settings")
django.setup()

from django.contrib.auth.models import User
from django.test import Client
from proveedor.models import Proveedor
from tipologia.models import TipoJoya
from producto.models import Producto
from movimiento.models import Venta, PagoVenta

def run_tests():
    print("Starting automated integration test for 'deudas' routes...")
    
    # Initialize Test Client
    client = Client()
    
    # Ensure a superuser/user exists and log them in
    user, created = User.objects.get_or_create(username="testadmin")
    if created:
        user.set_password("password123")
        user.is_superuser = True
        user.is_staff = True
        user.save()
    
    # Log in
    logged_in = client.login(username="testadmin", password="password123")
    print(f"Logged in: {logged_in}")
    if not logged_in:
        client.force_login(user)
        print("Forced login completed.")

    # Create dummy Tipologia, Proveedor, and Producto
    prov, _ = Proveedor.objects.get_or_create(nombre="Test Proveedor")
    tipo, _ = TipoJoya.objects.get_or_create(nombre="Test Tipo")
    prod, _ = Producto.objects.get_or_create(
        nombre="Test Producto",
        proveedor=prov,
        tipo=tipo,
        defaults={
            "costo_unitario": Decimal("50.00"),
            "precio_venta_unitario": Decimal("100.00"),
            "activo": True
        }
    )
    print(f"Using product: {prod} (cost: {prod.costo_unitario}, price: {prod.precio_venta_unitario})")

    # Clean up any existing test ventas/pagos to have a controlled environment
    Venta.objects.filter(cliente="Cliente Test Deuda").delete()

    # Step 1: Access Deudas List (should be empty of this client, or show others if existing)
    print("\n--- Step 1: Accessing Deudas List ---")
    response = client.get("/deudas/")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print("ERROR: /deudas/ returned non-200 status code!")
        if hasattr(response, "context") and response.context:
            print("Context:", response.context)
        print(response.content[:1000])
        return False

    # Step 2: Create a Venta with a_plazos = True
    print("\n--- Step 2: Creating a Venta (debt) ---")
    # Let's verify stock first. We need to create an entrance (IN) movement for the product so there is stock.
    from movimiento.models import Movimiento
    Movimiento.objects.create(
        tipo="IN",
        producto=prod,
        cantidad=10,
        precio_unitario=Decimal("50.00"),
        nota="Stock inicial para pruebas"
    )
    
    venta_data = {
        "cliente": "Cliente Test Deuda",
        "fecha": "2026-05-21T12:00",
        "producto": prod.id,
        "cantidad": 2,
        "precio_unitario": Decimal("120.00"),  # Custom price
        "a_plazos": True,
        "nota": "Nota de prueba de venta a plazos",
        "pago_inicial": Decimal("40.00")
    }
    
    response = client.post("/venta/registrar/", data=venta_data)
    print(f"Status (Redirect expected): {response.status_code}")
    if response.status_code not in [302, 200]:
        print("ERROR: /venta/registrar/ failed!")
        print(response.content[:1000])
        return False
        
    venta = Venta.objects.filter(cliente="Cliente Test Deuda").first()
    if not venta:
        print("ERROR: Venta was not created in database!")
        return False
    print(f"Created Venta ID: {venta.id}, Total: {venta.total}, Pagado: {venta.pagado}, Deuda: {venta.deuda}")

    # Step 3: Access Deudas List again (should contain our new Venta)
    print("\n--- Step 3: Accessing Deudas List (should contain the Venta) ---")
    response = client.get("/deudas/")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print("ERROR: /deudas/ failed after creating sale!")
        print(response.content[:1000])
        return False

    # Step 4: Access Venta Detalle Page
    print(f"\n--- Step 4: Accessing Venta Detalle for Venta ID: {venta.id} ---")
    response = client.get(f"/venta/{venta.id}/")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print("ERROR: /venta/detalle/ failed!")
        print(response.content[:1000])
        return False

    # Step 5: Register an Abono (Payment)
    print("\n--- Step 5: Registering an Abono ---")
    abono_data = {
        "monto": Decimal("50.00"),
        "fecha": "2026-05-21T13:00",
        "nota": "Abono parcial de prueba"
    }
    response = client.post(f"/venta/{venta.id}/pago/", data=abono_data)
    print(f"Status (Redirect expected): {response.status_code}")
    if response.status_code not in [302, 200]:
        print("ERROR: /venta/id/pago/ failed!")
        print(response.content[:1000])
        return False

    venta.refresh_from_db()
    print(f"After Abono: Pagado: {venta.pagado}, Deuda: {venta.deuda}")
    if venta.pagado != Decimal("90.00"): # 40 initial + 50 abono
        print(f"ERROR: Expected pagado to be 90.00, got {venta.pagado}")
        return False

    # Step 6: Access Venta Detalle Page again
    print("\n--- Step 6: Accessing Venta Detalle after Abono ---")
    response = client.get(f"/venta/{venta.id}/")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print("ERROR: /venta/detalle/ failed after abono!")
        print(response.content[:1000])
        return False

    # Step 6.5: Edit the Venta (debt)
    print("\n--- Step 6.5: Editing the Venta ---")
    venta_edit_data = {
        "cliente": "Cliente Test Editado",
        "fecha": "2026-05-21T12:00",
        "producto": prod.id,
        "cantidad": 3,
        "precio_unitario": Decimal("120.00"),
        "a_plazos": True,
        "nota": "Nota editada"
    }
    response = client.post(f"/venta/{venta.id}/editar/", data=venta_edit_data)
    print(f"Status (Redirect expected): {response.status_code}")
    if response.status_code not in [302, 200]:
        print("ERROR: /venta/id/editar/ failed!")
        print(response.content[:1000])
        return False

    venta.refresh_from_db()
    if venta.cliente != "Cliente Test Editado" or venta.cantidad != 3:
        print(f"ERROR: Venta was not correctly edited. Cliente: {venta.cliente}, Cantidad: {venta.cantidad}")
        return False
    print(f"After Edit: Total: {venta.total}, Pagado: {venta.pagado}, Deuda: {venta.deuda}")
    if venta.total != Decimal("360.00"):
        print(f"ERROR: Expected total to be 360.00, got {venta.total}")
        return False

    # Step 7: Delete a payment
    pago_to_delete = PagoVenta.objects.filter(venta=venta, nota="Abono parcial de prueba").first()
    if not pago_to_delete:
        print("ERROR: Abono was not created in database!")
        return False
    print(f"\n--- Step 7: Deleting Pago ID: {pago_to_delete.id} ---")
    response = client.post(f"/pago/{pago_to_delete.id}/eliminar/")
    print(f"Status (Redirect expected): {response.status_code}")
    if response.status_code not in [302, 200]:
        print("ERROR: /pago/id/eliminar/ failed!")
        print(response.content[:1000])
        return False

    venta.refresh_from_db()
    print(f"After deletion: Pagado: {venta.pagado}, Deuda: {venta.deuda}")
    if venta.pagado != Decimal("40.00"):
        print(f"ERROR: Expected pagado to be 40.00 after deletion, got {venta.pagado}")
        return False

    # Clean up test database objects
    venta.delete()
    User.objects.filter(username="testadmin").delete()
    print("\nAll integration tests PASSED successfully!")
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
