from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings

class LoginRequiredMiddleware:
    """
    Fuerza login en todo excepto:
    - login/logout
    - admin (Django ya protege)
    - staticfiles
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Permitir estáticos
        if path.startswith(getattr(settings, "STATIC_URL", "/static/")):
            return self.get_response(request)

        # Permitir admin (Django maneja auth ahí)
        if path.startswith("/admin/"):
            return self.get_response(request)

        # Permitir login/logout
        login_url = reverse("login")
        logout_url = reverse("logout")
        if path.startswith(login_url) or path.startswith(logout_url):
            return self.get_response(request)

        # Si no está logeado, redirigir
        if not request.user.is_authenticated:
            return redirect(f"{login_url}?next={request.get_full_path()}")

        return self.get_response(request)
