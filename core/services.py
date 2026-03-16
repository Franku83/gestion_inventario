import requests
import json
import re
from groq import Groq, RateLimitError
from decimal import Decimal
from django.core.cache import cache
from django.conf import settings
from django.db.models import Sum, Count, F
from producto.models import Producto
from proveedor.models import Proveedor
from movimiento.models import Movimiento, Venta

DOLAR_API_URL = "https://ve.dolarapi.com/v1/dolares"

def generar_descripcion_ia(producto):
    cache_key = f"prod_desc_{producto.id}"
    cached_desc = cache.get(cache_key)
    if cached_desc:
        return cached_desc

    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        prompt = f"Genera una descripción de lujo para una joya llamada {producto.nombre}, de tipo {producto.tipo} y del proveedor {producto.proveedor}."
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un experto en marketing de joyas de lujo."},
                {"role": "user", "content": prompt}
            ]
        )
        descripcion = completion.choices[0].message.content
        cache.set(cache_key, descripcion, 60 * 60 * 24)
        return descripcion
    except RateLimitError:
        return "El sistema está procesando muchas solicitudes en este momento. Por favor, intente de nuevo en unos minutos."
    except Exception as e:
        return f"Error al generar descripción: {str(e)}"

def sugerir_precio_ia(producto):
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        prompt = f"Basado en un costo unitario de {producto.costo_unitario} y el tipo de joya {producto.tipo}, sugiere un precio de venta unitario siguiendo márgenes de lujo. Devuelve solo el número decimal."
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un analista de precios para joyería de lujo. Responde solo con el valor numérico."},
                {"role": "user", "content": prompt}
            ]
        )
        respuesta = completion.choices[0].message.content.strip()
        numero = re.search(r"(\d+(\.\d+)?)", respuesta)
        return Decimal(numero.group(1)) if numero else None
    except Exception:
        return None

def analizar_riesgo_cobro_ia(venta):
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        prompt = f"Venta total: {venta.total}, Saldo pendiente: {venta.deuda}. Categoriza el riesgo (Bajo, Medio, Alto) y sugiere una acción de cobro."
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un experto en gestión de riesgos y cobranzas."},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error en análisis de riesgo: {str(e)}"

def generar_resumen_negocio_ia(datos):
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        prompt = f"Valor total inventario: {datos['valor_inventario']}, Deudas por cobrar: {datos['total_deudas']}, Ventas del mes: {datos['ventas_mes']}. Devuelve un análisis de 3 puntos sobre el estado financiero."
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un consultor financiero de alto nivel."},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error al generar resumen: {str(e)}"

def obtener_estadisticas_inventario():
    total_productos = Producto.objects.count()
    compras = Movimiento.objects.filter(tipo="IN", anulada=False).values("producto_id").annotate(total_in=Sum("cantidad"))
    ventas = Venta.objects.values("producto_id").annotate(total_out=Sum("cantidad"))
    compras_map = {c["producto_id"]: c["total_in"] for c in compras}
    ventas_map = {v["producto_id"]: v["total_out"] for v in ventas}
    valor_total = Decimal("0.00")
    for p in Producto.objects.all():
        qty = compras_map.get(p.id, 0) - ventas_map.get(p.id, 0)
        if qty > 0:
            valor_total += Decimal(qty) * p.costo_unitario
    proveedor_top = Proveedor.objects.annotate(num_prod=Count("productos")).order_by("-num_prod").first()
    return {
        "total_productos": total_productos,
        "valor_stock_usd": float(valor_total),
        "proveedor_con_mas_articulos": proveedor_top.nombre if proveedor_top else "Ninguno"
    }

def asistente_inventario_ia(query):
    try:
        client = Groq(api_key=settings.GROQ_API_KEY)
        stats = obtener_estadisticas_inventario()
        context = f"Estadísticas actuales: {stats}"
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"Eres un asistente de inventario. {context}"},
                {"role": "user", "content": query}
            ]
        )
        return completion.choices[0].message.content
    except RateLimitError:
        return "El sistema está procesando muchas solicitudes en este momento. Por favor, intente de nuevo en unos minutos."
    except Exception as e:
        return f"Error en el asistente: {str(e)}"

def obtener_usd_bs_rate():
    cache_key = "usd_bs_rate"
    rate = cache.get(cache_key)
    if rate:
        return Decimal(rate)

    try:
        response = requests.get(DOLAR_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()

        for item in data:
            if item.get("fuente") == "oficial":
                promedio = item.get("promedio")
                if promedio:
                    rate = Decimal(str(promedio))
                    cache.set(cache_key, str(rate), 60 * 30)
                    return rate
    except Exception:
        pass

    return Decimal("0.00")
