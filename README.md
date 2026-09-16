# Joyerías Inventario

Sistema interno de inventario, compras, ventas a plazo y cobranza para joyería. Django + Postgres (SQLite en local).

## Correr en local

```bash
cp .env.example .env   # y completa SECRET_KEY (ver el archivo cómo generarla)
.venv/bin/pip install -r requirements.txt
make migrate           # o: .venv/bin/python manage.py migrate
make run               # http://127.0.0.1:8000 (crea tu usuario con createsuperuser)
```

Comandos: `make check` · `make test` · `make migrate` · `make run`.

## Uso diario (2 clics cada flujo)

- **Vender:** Inventario → *Vender* (ya trae el producto) o Venta → *Registrar venta*. Una o varias filas; marca *A plazos* por fila; *pago inicial* solo con 1 fila. El precio se auto-completa.
- **Comprar:** Inventario → *Comprar* o Compra → *Registrar compra*. Producto existente o *crear nuevo* en la misma fila; *+ Agregar* para varias.
- **Cobrar:** Deudas → *Abonar* (vuelve a la bandeja al guardar). El sistema bloquea abonos mayores a la deuda.
- **Corregir / revertir:** *Editar* corrige datos; **Anular** revierte stock y excluye de métricas sin borrar historial. No existe borrado físico de compras.

Reglas: `stock = compras no anuladas − ventas no anuladas` (`movimiento/services.py`, única fuente). `deuda = total − pagado > 0`, sin importar si es a plazos.

## Estructura

```
core/        dashboard, inventario, base, login required
proveedor/   CRUD proveedores      tipologia/  CRUD tipos de joya
producto/    CRUD productos        movimiento/ compras, ventas, pagos, deudas + services (stock/deuda)
```

## Deploy en Railway

1. Sube la rama (o `main`) a GitHub y crea el servicio desde el repo.
2. Agrega plugin **Postgres** y enlázalo al servicio (inyecta `DATABASE_URL`).
3. En *Variables* define: `DEBUG=0`, `SECRET_KEY=<50+ caracteres>`, `ALLOWED_HOSTS=tu-app.up.railway.app`, `CSRF_TRUSTED_ORIGINS=https://tu-app.up.railway.app`.
4. Deploy: el `Procfile` corre `collectstatic + migrate + gunicorn` solo.
5. Verifica: `.../admin/` abre y `check --deploy` está en 0 issues (ver CHANGELOG v2.0).

## Migrar datos SQLite → Postgres (una vez)

```bash
# 1. Respaldo local
.venv/bin/python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.permission -e admin.logentry -e sessions > backup.json
# 2. Apunta .env a Postgres de Railway (DATABASE_URL=...) y:
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata backup.json
.venv/bin/python manage.py createsuperuser
```

## Notas

- Tasa USD→Bs referencial vía `ve.dolarapi.com` (caché 30 min; `0.00` si falla).
- Sin features de IA (eliminadas en v2.0, ver CHANGELOG).
- Detalle del refactor por sprints: `plan.md`.
