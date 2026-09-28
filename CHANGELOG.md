# Changelog

## Sin versión — bajas de stock + fechas en inventario (2026-09-28, `main`)

- Nuevo tipo `Movimiento.ADJ` ("Baja / Ajuste"): saca piezas del stock **sin vender** (no toca vendido, ganancia ni deudas). Botón **Baja** en cada fila de inventario + lista **Bajas de stock** en menú Compra, con anulación reversible (devuelve stock). Todo el cálculo de stock (`get_stock_map`, inventario, dashboard, `producto_list`, estadísticas) resta las bajas no anuladas.
- Inventario muestra **Últ. ingreso** y **Últ. venta** por producto (útil para decidir qué limpiar).
- Tests 27 → 33 (`movimiento/test_ajustes.py`, 6 nuevos).

## v2.0-refactor (2026-09-16) — rama `refactor/s1-desacoplar`

Refactor completo sin reescribir: el sistema hace lo mismo, más simple y por dominio.

- **Elimina IA** (5 servicios Groq, 5 vistas, 5 URLs, 3 campos + migraciones reversa, `groq` de requirements, `GROQ_API_KEY` fuera de settings/`.env`).
- **S0:** CI GitHub Actions, `Makefile`, `movimiento/services.py` como única fuente de stock/deuda, tests 3 → 7.
- **S1:** `core/views.py` 770 → ~190 (+re-exports); cada app con views/forms/urls propios (`proveedor`, `tipologia`, `producto`, `movimiento`); `core/urls` solo includes.
- **S2:** compras en 1 flujo (formset + crear-inline); fuera `CompraUnificadaForm`, `compra_multiple`, borrado físico; solo Anular + Editar.
- **S3:** ventas en 1 flujo (`a_plazos`/`fecha` por fila, pago inicial 1 fila); fuera `VentaForm` single y `venta_lote`; `pago_create` bloquea sobrepago y vuelve a `?next=`; definición única de deuda (dashboard alineado).
- **S4:** inventario con [Vender][Comprar] + prefill `?producto=` + solo-stock por defecto; dashboard con Por cobrar + Stock inmovilizado; `resumen_mensual` a ORM; navbar con Catálogos.
- **S5:** `check --deploy` en 0 issues (`SECURE_SSL_REDIRECT`, storage Whitenoise con manifest, logging a consola), `collectstatic` en Procfile, fuera `joyerias_inventario.zip` del repo, README + este changelog. Tests 27/27.

⚠️ **Rupturas intencionales:** URLs `compra/registrar-multiple/`, `venta/registrar-lote/` (redigen al flujo único), `compra/<id>/eliminar/` y reversas `venta_lote`, `compra_delete` (404). Campos IA eliminados de la DB.
