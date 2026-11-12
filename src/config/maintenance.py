from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.cache import add_never_cache_headers


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.MAINTENANCE_MODE:
            return self.get_response(request)

        response = HttpResponse(render_to_string("errors/maintenance.html"), status=503)
        add_never_cache_headers(response)
        return response
