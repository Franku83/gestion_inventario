import requests
from decimal import Decimal
from django.core.cache import cache

DOLAR_API_URL = "https://ve.dolarapi.com/v1/dolares"


def obtener_usd_bs_rate():
    """
    Devuelve tasa USD → Bs usando DolarAPI.
    Cachea 30 minutos.
    """
    cache_key = "usd_bs_rate"

    # 1) Revisar cache
    rate = cache.get(cache_key)
    if rate:
        return Decimal(rate)

    # 2) Consultar API
    try:
        response = requests.get(DOLAR_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()

        for item in data:
            if item.get("fuente") == "oficial":
                promedio = item.get("promedio")
                if promedio:
                    rate = Decimal(str(promedio))
                    cache.set(cache_key, str(rate), 60 * 30)  # 30 minutos
                    return rate

    except Exception:
        pass

    # 3) Fallback: si falla, intenta usar última tasa guardada
    return Decimal("0.00")
