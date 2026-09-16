# Plan de Refactorización — Joyerías Inventario (Django)

> Objetivo: hacerlo **más práctico** sin reescribir a TypeScript.
> "Práctico" = vender en ≤2 clics, comprar en ≤2 clics, ver deudas en 1 sola bandeja, stock siempre confiable.

## 0. Estado actual (verificado 2026-09-16)

| Punto | Evidencia | Problema |
|---|---|---|
| God module | `core/views.py:770` con 25 vistas, `core/forms.py:354` con 10 forms | Todo acoplado en `core`; `proveedor/`, `producto/`, `movimiento/`, `tipologia/` tienen `views.py` de 3 líneas (vacías) |
| Stock frágil | `core/views.py:42` `_get_stock_map()` + `Subquery(OuterRef)` en `inventario()` + validación duplicada en `VentaForm`, `VentaEditForm`, `ItemVentaForm`, `venta_create`, `venta_update`, `venta_lote` | 6 lugares calculan stock distinto; bug histórico JOIN cartesiano (`554ec46`) puede regresar |
| Deuda ambigua | `dashboard()` filtra `a_plazos=True`; `deudas_list()` filtra `deuda_calc__gt=0` | Dos definiciones de "deuda" → confusión usuario |
| Flujos duplicados compra | `compra_create` + `compra_multiple` + `CompraUnificadaForm` + `CompraEditForm` + `compra_list.html` + `compra_multiple.html` + `compra_unificada.html` | Usuario no sabe cuál usar |
| Flujos duplicados venta | `venta_create` + `venta_lote` + `venta_form.html` + `venta_lote.html` + `deudas_list.html` + `venta_detalle.html` + `abono_form.html` | Vender, ver deuda, abonar son 3 pantallas separadas |
| Templates | 19 en `core/templates/core/`, Tailwind por CDN en `base.html`, sin componentes ni paginación uniforme | Mantenimiento caro, UI inconsistente |
| Tests | Solo `core/tests.py` (3 tests `VentaAnuladaTests`) + `test_all_deudas.py` manual fuera de suite | Sin red de seguridad para refactorizar |
| Config | `settings.py:136`, `dj-database-url` + SQLite local, `Procfile` Railway, `.env` + `.env.example` | OK base, falta CI y `check --deploy` limpio |

**Regla de oro del refactor:** ningún sprint cambia el modelo de datos salvo que se diga explícito. Primero mover código, después simplificar UX, al final optimizar.

## 1. Arquitectura objetivo

```
core/         → solo shell: dashboard, inventario (lectura), base.html, middleware, services/tasa USD
proveedor/    → CRUD proveedor (views+forms+urls+templates propios)
tipologia/    → CRUD tipo joya (idem)
producto/     → CRUD producto + stock read-model
movimiento/   → compras (IN) + ventas + pagos + deudas (TODO lo transaccional)
joyerias_inventario/ → settings/urls raíz solo include()
```

```
                 ┌─────────────┐
                 │  dashboard  │  (core, solo lectura KPIs)
                 └──────┬──────┘
                        │
┌───────────┐  ┌────────┴────────┐  ┌─────────────┐
│ producto/ │──│ stock_service   │──│ movimiento/ │
│ +proveedor│  │ (ÚNICA fuente)  │  │ compra/venta│
│ +tipologia│  │ IN - Venta no   │  │ pago/deuda  │
└───────────┘  │ anulada         │  └─────────────┘
               └─────────────────┘
```

**Servicios únicos (nuevo `movimiento/services.py`):**
- `get_stock(producto_id) -> int` / `get_stock_map(ids) -> dict`
- `get_deuda(venta) -> Decimal` / `ventas_con_deuda_qs()` (un solo queryset anotado)
- Nada de IA. Nada de `Groq`. Ya eliminado en `a707ebc`.

## 2. Sprints

> Duración sugerida: 1 semana por sprint. Orden estrictamente secuencial.
> Cada sprint termina con `manage.py check + manage.py test` en verde y demo de 10 min con un usuario real.

---

### Sprint 0 — Base segura (0.5 semana) [pre-requisito]

**Objetivo:** poder refactorizar sin miedo.

- [ ] Congelar scope: no nuevos features durante S0–S2. Solo fixes bloqueantes.
- [ ] Mover `test_all_deudas.py` a `movimiento/tests/test_deudas.py` como `TestCase` real (hoy es script manual con `Client()`).
- [ ] Agregar `core/tests/test_stock.py`: 3 casos (stock 10-3=7, anulada devuelve stock, lote no permite oversell).
- [ ] CI mínimo: `.github/workflows/django.yml` → `pip install -r requirements.txt + check + test`.
- [ ] `make` o `scripts/`: `check`, `test`, `migrate`, `run`.
- [ ] Métrica base: anotar tiempo "registrar venta" (clics) y queries de `deudas_list` (django-debug-toolbar o `assertNumQueries`).

**Archivos:** `.github/workflows/django.yml`, `movimiento/tests/*`, `core/tests/*`, `Makefile`
**Aceptación:** `pytest`/`manage.py test` corre en CI; 6+ tests verdes; demo: mostrar CI en verde.

---

### Sprint 1 — Desacoplar dominio (1 semana) [el más importante]

**Objetivo:** vaciar `core/views.py` (<150 líneas) moviendo cada vista a su app. Sin cambiar UX todavía.

- [ ] Crear `proveedor/{views,forms,urls}.py` y mover `proveedor_list/create/update/delete` desde `core/`. `core/urls.py` → `include("proveedor.urls")`.
- [ ] Igual para `tipologia/` (`tipo_*`) y `producto/` (`producto_*`).
- [ ] Crear `movimiento/{views_compras,views_ventas,forms,urls}.py` y mover `compra_*`, `venta_*`, `pago_*`, `deudas_list`, `resumen_mensual`.
- [ ] `core/` queda solo con: `dashboard`, `inventario`, `middleware.py`, `services.py` (tasa USD).
- [ ] Crear `movimiento/services.py` con `get_stock_map()` (mover desde `core/views.py:42`) y hacer que **todas** las validaciones lo usen. Borrar cálculo duplicado en `VentaForm.clean`, `VentaEditForm.clean`, `ItemVentaForm.clean` → llamar al servicio.
- [ ] Mover templates: `core/templates/core/proveedor_*.html` → `proveedor/templates/proveedor/` (idem tipos, producto, movimiento). Dejar re-export temporal si rompe `{% url %}` (no renombrar URLs en este sprint).
- [ ] Verificar que `grep -n "from core" movimiento/ producto/` no importe vistas/forms de core.

**Archivos:** `core/views.py`, `core/urls.py`, `*/views.py`, `*/urls.py`, `joyerias_inventario/urls.py`, `movimiento/services.py`
**Aceptación:** `wc -l core/views.py` < 200; todas las URLs existentes responden igual (`test_all_deudas` sigue verde); cero imports circulares.

---

### Sprint 2 — Compras: un solo flujo (1 semana) ✅ HECHO (2026-09-16, rama `refactor/s1-desacoplar`)

**Objetivo:** de 3 formas de comprar → 1.

- [x] Fusión (sin borrar capacidad): el formset (`ItemCompraForm` con crear-nuevo inline + "+ agregar fila") pasa a ser LA pantalla "Registrar compra" (`compra/registrar/` → `core/compra_form.html`). La vieja `compra/registrar-multiple/` redirige (RedirectView, no 404).
- [x] `CompraUnificadaForm` eliminado; `CompraEditForm` → `CompraForm` (alias compat); `CompraMultipleFormSet` → `CompraFormSet` (alias compat) en `movimiento/forms.py`.
- [x] `compra_list`: solo Editar + Anular (quitado "Eliminar" físico + vista `compra_delete` + URL; anular conserva historial).
- [x] Templates: `compra_unificada.html` borrado; `compra_multiple.html` → `compra_form.html` retitulado; navbar sin "en lote" (desktop + mobile).
- [x] Tests `movimiento/test_compras.py` (6): existente, nuevo inline, varias filas, anular excluye stock, redirect URL vieja, borrado físico 404/NoReverseMatch.

**Aceptación:** registrar compra ≤2 clics; `grep compra_multiple/CompraUnificadaForm/compra_delete` = solo comentarios + test negativo + aliases; 13/13 tests verdes.

---

### Sprint 3 — Ventas + Deudas + Pagos: una sola bandeja (1 semana) ✅ HECHO (2026-09-16, rama `refactor/s1-desacoplar`)

**Objetivo:** el módulo que más quejas genera. De 4 pantallas → 2.

- [x] **Definición única de deuda** escrita en `movimiento/services.py` docstring: `deuda = total - pagado > 0 AND anulada=False`; `a_plazos` solo etiqueta. `dashboard()` usa `ventas_con_deuda_qs()` (mismo queryset que la bandeja).
- [x] Fusionado `venta_create` + `venta_lote`: una sola vista formset (1 fila + "+ Agregar venta"), `a_plazos` + `fecha` por fila, `pago_inicial` a nivel página (solo válido con 1 fila). `venta/registrar-lote/` redirige; `VentaForm` single y `venta_lote.html` eliminados (`VentaLoteFormSet` queda como alias). Validación intra-lote vía `validar_stock_lote()`.
- [x] `deudas_list` = **bandeja única**; botón "Abonar" con `?next=` para volver a la bandeja tras guardar (sin pasar por detalle en el 80%). `venta_detalle` queda para historial/auditoría.
- [x] `pago_create`: bloquea `monto > deuda` (error, no warning) + bloquea abono si `anulada` + respeta `?next=` seguro (`url_has_allowed_host_and_scheme`); `abono_form.html` muestra deuda y preserva `next`.
- [ ] `venta_update` separada se mantiene (edición con `VentaEditForm` + `venta_form.html`); fusionarla en detalle queda diferido (pantalla de edición ya es 1 solo formulario, sin duplicación de flujos de alta).
- [x] Tests `movimiento/test_ventas.py` (8): única+pago inicial, multifila con modalidad por fila, pago inicial multifila rechazado, oversell acumulado, redirect URL vieja, sobrepago bloqueado, `?next=` a deudas, contado con deuda en bandeja + dashboard. `test_all_deudas.py` manual eliminado (superseded). `core/tests.py` usa `VentaEditForm`.

**Aceptación:** vender+cobrar demo en <60 seg; `grep venta_lote` = solo comentarios + alias + test negativo; 21/21 tests verdes.

---

### Sprint 4 — Inventario + Dashboard prácticos (1 semana) ✅ HECHO (2026-09-16, rama `refactor/s1-desacoplar`)

**Objetivo:** que el dashboard responda "¿qué hago hoy?".

- [x] `inventario`: columna Acciones **[Vender][Comprar]** (`venta_create?producto=X` / `compra_create?producto=X` con prefill de la 1ª fila); `solo_stock` ON por defecto (form envía off/on explícito con hidden+checkbox); paginación conserva `q/proveedor/tipo/solo_stock`.
- [x] `dashboard`: 4 KPIs intactos + 2 listas accionables: **Por cobrar** (top 5 `ventas_con_deuda_qs`) y **Stock inmovilizado** (stock>0 sin ventas 90 días, ordenado por valor, con link Vender). Sin residuos IA (verificado).
- [x] `resumen_mensual`: agregación en ORM (`TruncMonth` + `Sum` + `Count`), mismo formato de salida; filtro año con default actual.
- [x] `base.html`: Proveedores/Tipos colapsados en **Catálogos** (desktop dropdown + sección mobile). Tailwind CDN se deja como está (compilarlo = pipeline Node; diferido a S5 si se quiere).
- [x] Paginación 25 uniforme verificada en inventario/compra/deudas/proveedor/tipo/producto.
- [x] Tests `core/test_sprint4.py` (6): solo_stock default/off, links Vender/Comprar, prefill venta+compra (+id inválido), tops dashboard, inmovilizado 90d, resumen ORM con totales.

**Aceptación:** 27/27 tests verdes; `check` limpio.

---

### Sprint 5 — Hardening + Deploy limpio (0.5 semana) ✅ HECHO (2026-09-16, rama `refactor/s1-desacoplar`)

**Objetivo:** dejarlo production-ready.

- [x] `check --deploy` en **0 issues** con env prod-like (`SECURE_SSL_REDIRECT=1` tras proxy header, resto ya existía).
- [x] `SECRET_KEY`/`ALLOWED_HOSTS`/`DATABASE_URL` solo por env (falla en prod si faltan); `Procfile` = `collectstatic + migrate + gunicorn`; storage Whitenoise con manifest (verificado `collectstatic` OK); logging a consola en prod.
- [x] `.env.example` documentado (generar clave, variables Railway, `DATABASE_URL` del plugin Postgres); restore SQLite→Postgres documentado en README (dumpdata/loaddata; ejecutar por operador).
- [x] Limpieza: `joyerias_inventario.zip` fuera del repo (`git rm`); `graphify-out/`, `venv/`, `__pycache__`, `db.sqlite3`, `staticfiles/` ignorados y sin rastros en git; `requirements.txt` sin `groq`.
- [x] README de 1 página + CHANGELOG con rupturas intencionales.
- [x] Tag `v2.0-refactor`.

**Aceptación:** `check --deploy` OK con `DEBUG=0`; tests 27/27; pendiente operador: definir vars en Railway + deploy + migración de datos (pasos en README).

---

## 3. Backlog priorizado (si sobra tiempo, en este orden)

1. Búsqueda global navbar (`?q` busca producto/cliente/proveedor).
2. Exportar `deudas_list` a CSV/Excel (cobranza en campo).
3. Auditoría: quién creó/anuló cada venta (`created_by`, `anulada_por`, `anulada_at`).
4. Permisos por rol (vendedor no puede anular/eliminar, solo admin).
5. PWA offline lectura inventario (solo si piden mobile).

## 4. Fuera de alcance (no hacer)

- Reescribir a TypeScript/Next.js.
- Reintroducir IA (descripciones, precios, riesgo).
- Nuevo modelo `Stock` con triggers (mantener `IN - Venta` calculado; solo crear tabla si Sprint 4 demuestra lentitud real).
- Multi-moneda contable (solo mostrar Bs referencial con tasa `ve.dolarapi`).
- Facturación fiscal.

## 5. Definition of Done (todos los sprints)

- [ ] ` manage.py check` verde.
- [ ] `manage.py test` verde (incluye tests nuevos del sprint).
- [ ] Sin imports `core.views` desde apps de dominio.
- [ ] Sin queries N+1 nuevas (`deudas_list`, `inventario`, `dashboard` con `select_related`/`annotate`).
- [ ] URLs viejas siguen funcionando o tienen redirect (no 404 silenciosos).
- [ ] Demo 10 min con usuario + 1 ajuste aplicado.

## 6. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Romper cálculo stock al mover código | S0 congela tests de stock; S1 no cambia lógica, solo mueve archivos |
| Usuarios apegados a "compra en lote" | S2 valida uso real antes de borrar; fusión en vez de borrado si hay duda |
| Migraciones conflictivas | No tocar modelos en S1–S3; solo S4/S5 si hace falta, una migración por cambio |
| Scope creep ("ya que estamos, agreguen X") | Backlog §3; todo lo demás a "Fuera de alcance" §4 |

## 7. Comandos

```bash
# dev
.venv/bin/python manage.py check
.venv/bin/python manage.py test --verbosity=1
.venv/bin/python manage.py runserver

# verificar un sprint
wc -l core/views.py                    # Sprint 1: <200
grep -rn "compra_multiple" --include="*.py" --include="*.html" . | grep -v .venv
grep -rn "from core" movimiento/ producto/ proveedor/ tipologia/ --include="*.py"
.venv/bin/python manage.py check --deploy  # Sprint 5 con DEBUG=0
```

## 8. Cómo empezar mañana (checklist día 1)

- [ ] Crear rama `refactor/s1-desacoplar`.
- [ ] Crear `movimiento/services.py` con `get_stock_map` movido tal cual.
- [ ] Mover `proveedor_*` (views+forms+urls+templates) y abrir PR chico solo de eso.
- [ ] Mover `tipologia_*`, luego `producto_*`, luego `movimiento_*`, un PR por app.
- [ ] Cerrar Sprint 1 cuando `core/views.py` solo tenga `dashboard` + `inventario`.
