from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AssessmentForm
from .models import Assessment, AssessmentType


def _assessment_queryset(user, query=""):
    assessments = Assessment.objects.filter(owner=user).prefetch_related(
        "assessment_types"
    ).select_related("technique")
    if query:
        assessments = assessments.annotate(
            observations_text=Cast("observations", output_field=TextField())
        ).filter(
            Q(subject__icontains=query)
            | Q(topic__icontains=query)
            | Q(observations_text__icontains=query)
            | Q(assessment_types__name__icontains=query)
            | Q(technique__name__icontains=query)
        )
    return assessments.distinct()


def _render_index(request, *, form=None, editing=None, status=200):
    query = request.GET.get("q", "").strip()
    assessment_types = AssessmentType.objects.select_related("default_technique")
    return render(
        request,
        "assessments/index.html",
        {
            "assessments": _assessment_queryset(request.user, query),
            "assessment_form": form or AssessmentForm(),
            "editing_assessment": editing,
            "query": query,
            "default_techniques": {
                str(item.pk): item.default_technique.name for item in assessment_types
            },
        },
        status=status,
    )


@login_required
def index(request: HttpRequest) -> HttpResponse:
    return _render_index(request)


@login_required
def create(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("assessments:index")
    form = AssessmentForm(request.POST)
    if form.is_valid():
        form.save(owner=request.user)
        messages.success(request, "Avaliação registrada com sucesso.")
        return redirect("assessments:index")
    return _render_index(request, form=form, status=422)


@login_required
def update(request: HttpRequest, pk: int) -> HttpResponse:
    assessment = get_object_or_404(Assessment, pk=pk, owner=request.user)
    if request.method != "POST":
        return redirect("assessments:index")
    form = AssessmentForm(request.POST, instance=assessment)
    if form.is_valid():
        form.save()
        messages.success(request, "Avaliação atualizada com sucesso.")
        return redirect("assessments:index")
    return _render_index(request, form=form, editing=assessment, status=422)
