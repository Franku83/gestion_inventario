from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect


class LoginRequiredMiddleware:
    """
    Bloquea toda la app detrás del login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return self.get_response(request)

        path = request.path_info or "/"

        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
        allowed_prefixes = [
            login_url.rstrip("/") + "/",
            "/accounts/logout/",
            "/admin/",
            "/static/",
            "/media/",
        ]

        if any(path.startswith(p) for p in allowed_prefixes):
            return self.get_response(request)

        if path == login_url:
            return self.get_response(request)

        return redirect(f"{login_url}?next={path}")
