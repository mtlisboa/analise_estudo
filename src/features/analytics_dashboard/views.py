from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .services import build_dashboard


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "analytics_dashboard/dashboard.html",
        build_dashboard(request.user, request.GET),
    )
