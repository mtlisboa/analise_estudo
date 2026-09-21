from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GenerateAnalysisForm
from .models import SavedAnalysis
from .services import build_dashboard


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "analytics_dashboard/index.html",
        {"saved_analyses": SavedAnalysis.objects.filter(created_by=request.user)},
    )


@login_required
def generate_analysis(request: HttpRequest) -> HttpResponse:
    form = GenerateAnalysisForm(
        request.POST or None,
        user=request.user,
        initial=request.GET if request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        analysis_context = build_dashboard(request.user, form.analysis_params)
        title = form.cleaned_data["title"].strip() or (
            f'{analysis_context["scope_title"]} · '
            f'{analysis_context["analytics_payload"]["periodLabel"]}'
        )
        saved_analysis = SavedAnalysis.objects.create(
            title=title,
            scope_title=analysis_context["scope_title"],
            period_label=analysis_context["analytics_payload"]["periodLabel"],
            filters=analysis_context["filters"],
            snapshot={
                "metrics": analysis_context["metrics"],
                "ranking": analysis_context["ranking"],
                "analytics_payload": analysis_context["analytics_payload"],
            },
            created_by=request.user,
        )
        messages.success(request, "Análise gerada e salva com sucesso.")
        return redirect("analytics-dashboard:detail", pk=saved_analysis.pk)
    return render(request, "analytics_dashboard/generate.html", {"form": form})


@login_required
def analysis_detail(request: HttpRequest, pk: int) -> HttpResponse:
    saved_analysis = get_object_or_404(
        SavedAnalysis,
        pk=pk,
        created_by=request.user,
    )
    return render(
        request,
        "analytics_dashboard/dashboard.html",
        {
            "saved_analysis": saved_analysis,
            "scope_title": saved_analysis.scope_title,
            "metrics": saved_analysis.snapshot["metrics"],
            "ranking": saved_analysis.snapshot["ranking"],
            "analytics_payload": saved_analysis.snapshot["analytics_payload"],
        },
    )
