from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GenerateAnalysisForm, SaveAnalysisForm
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
    if request.method == "POST" and request.POST.get("action") == "save":
        save_form = SaveAnalysisForm(request.POST, user=request.user)
        if save_form.is_valid():
            analysis_context = build_dashboard(request.user, save_form.analysis_params)
            selection_label = save_form.cleaned_data["selection_label"].strip()
            if analysis_context["filters"]["selected_students"] and selection_label:
                analysis_context["scope_title"] = selection_label
            title = save_form.cleaned_data["title"].strip() or (
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
            messages.success(request, "Análise salva com sucesso.")
            return redirect("analytics-dashboard:detail", pk=saved_analysis.pk)

        filter_form = GenerateAnalysisForm(request.POST, user=request.user)
        if filter_form.is_valid():
            analysis_context = build_dashboard(request.user, filter_form.analysis_params)
            return _render_analysis(
                request,
                analysis_context,
                is_preview=True,
                save_form=save_form,
            )
        form = filter_form
        return render(request, "analytics_dashboard/generate.html", {"form": form})

    form = GenerateAnalysisForm(
        request.POST or None,
        user=request.user,
        initial=request.GET if request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        analysis_context = build_dashboard(request.user, form.analysis_params)
        default_title = (
            f'{analysis_context["scope_title"]} · '
            f'{analysis_context["analytics_payload"]["periodLabel"]}'
        )
        save_form = SaveAnalysisForm(
            user=request.user,
            initial={**form.analysis_params, "title": default_title},
        )
        return _render_analysis(
            request,
            analysis_context,
            is_preview=True,
            save_form=save_form,
        )
    return render(request, "analytics_dashboard/generate.html", {"form": form})


@login_required
def analysis_detail(request: HttpRequest, pk: int) -> HttpResponse:
    saved_analysis = get_object_or_404(
        SavedAnalysis,
        pk=pk,
        created_by=request.user,
    )
    return _render_analysis(
        request,
        {
            "scope_title": saved_analysis.scope_title,
            "metrics": saved_analysis.snapshot["metrics"],
            "ranking": saved_analysis.snapshot["ranking"],
            "analytics_payload": saved_analysis.snapshot["analytics_payload"],
        },
        saved_analysis=saved_analysis,
    )


def _render_analysis(
    request: HttpRequest,
    analysis_context: dict,
    *,
    saved_analysis: SavedAnalysis | None = None,
    is_preview: bool = False,
    save_form: SaveAnalysisForm | None = None,
) -> HttpResponse:
    return render(
        request,
        "analytics_dashboard/dashboard.html",
        {
            "saved_analysis": saved_analysis,
            "is_preview": is_preview,
            "save_form": save_form,
            "scope_title": analysis_context["scope_title"],
            "metrics": analysis_context["metrics"],
            "ranking": analysis_context["ranking"],
            "analytics_payload": analysis_context["analytics_payload"],
        },
    )
