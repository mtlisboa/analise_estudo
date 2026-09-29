from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from features.users_manager.models import Organization
from .forms import BatchForm, FORMS, LABELS, PeriodForm, RevisionForm
from .models import Lesson, Offer, Period, Requirement, Slot, Student, Teacher
from .services import authorize, distribute, generate_timetable, import_students, mutate, pending_issues, publish, validate_existing


def scoped_objects(period, kind):
    if kind == "period":
        return Period.objects.filter(pk=period.pk)
    if kind in ("offer", "student", "slot", "teacher"):
        model = {"offer": Offer, "student": Student, "slot": Slot, "teacher": Teacher}[kind]
        return model.objects.filter(period=period)
    if kind == "requirement":
        return Requirement.objects.filter(offer__period=period)
    if kind == "lesson":
        return Lesson.objects.filter(requirement__offer__period=period)
    raise Http404


def get_period(actor, pk):
    identity = authorize(actor)
    return get_object_or_404(Period, pk=pk, organization=identity.organization)


def error_text(exc):
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    if isinstance(exc, ProtectedError):
        return "Este registro está em uso. Remova ou altere seus vínculos primeiro."
    if isinstance(exc, IntegrityError):
        return "Já existe um registro com estes dados, ou há um vínculo incompatível."
    return "Outra operação está em andamento. Recarregue a página e tente novamente."


ERRORS = (ValidationError, IntegrityError, OperationalError)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    identity = authorize(request.user)
    form = PeriodForm(request.POST or None)
    if request.method == "POST":
        form.instance.organization = identity.organization
        if form.is_valid():
            try:
                with transaction.atomic():
                    Organization.objects.select_for_update().get(pk=identity.organization_id)
                    obj = form.save()
                return redirect("planning:detail", pk=obj.pk)
            except ERRORS as exc:
                form.add_error(None, error_text(exc))
    return render(request, "planning/index.html", {
        "form": form, "periods": Period.objects.filter(organization=identity.organization),
    })


@login_required
@never_cache
@require_http_methods(["GET"])
def detail(request, pk):
    period = get_period(request.user, pk)
    roster = period.students.select_related("offer")
    query = request.GET.get("q", "").strip()[:100]
    if query:
        from django.db.models import Q
        roster = roster.filter(Q(name__icontains=query) | Q(registration__icontains=query))
    lessons = Lesson.objects.filter(requirement__offer__period=period).select_related(
        "slot", "requirement__offer", "requirement__teacher__account__user")
    selected_teacher = request.GET.get("teacher", "")
    if selected_teacher.isdigit():
        lessons = lessons.filter(requirement__teacher_id=int(selected_teacher))
    return render(request, "planning/detail.html", {
        "period": period, "offers": period.offers.prefetch_related("students"),
        "student_page": Paginator(roster, 50).get_page(request.GET.get("page")), "query": query,
        "teachers": period.teachers.select_related("account__user").prefetch_related("availability"),
        "slots": period.slots.all(), "requirements": Requirement.objects.filter(offer__period=period).select_related(
            "offer", "teacher__account__user").prefetch_related("lessons"),
        "lessons": lessons, "selected_teacher": selected_teacher,
        "issues": pending_issues(period), "batch_form": BatchForm(initial={"revision": period.revision}),
        "dirty": period.published_revision != period.revision,
    })


class InvalidForm(Exception):
    def __init__(self, form):
        self.form = form


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit(request, pk, kind, item=None):
    period = get_period(request.user, pk)
    if kind not in FORMS or (kind == "period" and item != period.pk):
        raise Http404
    instance = get_object_or_404(scoped_objects(period, kind), pk=item) if item else None
    form = FORMS[kind](request.POST if request.method == "POST" else None, period=period, instance=instance)
    if request.method == "POST":
        revision_form = RevisionForm(request.POST)
        if not revision_form.is_valid():
            form.is_valid()
            form.add_error(None, "Versão inválida. Recarregue a página.")
        else:
            def save(locked_period):
                obj = get_object_or_404(scoped_objects(locked_period, kind), pk=item) if item else None
                bound = FORMS[kind](request.POST, period=locked_period, instance=obj)
                if not bound.is_valid():
                    raise InvalidForm(bound)
                saved = bound.save()
                # Validate using edited dates when the period itself changed.
                validate_existing(saved if kind == "period" else locked_period)
                return saved
            try:
                mutate(request.user, period.pk, revision_form.cleaned_data["revision"], save)
                messages.success(request, "Alteração salva no planejamento. Publique para atualizar as turmas.")
                return redirect("planning:detail", pk=period.pk)
            except InvalidForm as exc:
                form = exc.form
            except ERRORS as exc:
                form = FORMS[kind](request.POST, period=period, instance=instance)
                form.is_valid()
                form.add_error(None, error_text(exc))
    return render(request, "planning/form.html", {"form": form, "period": period,
        "title": ("Editar " if item else "Adicionar ") + LABELS[kind]})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def delete(request, pk, kind, item):
    period = get_period(request.user, pk)
    if kind == "period":
        raise Http404
    instance = get_object_or_404(scoped_objects(period, kind), pk=item)
    form = RevisionForm(request.POST or None, initial={"revision": period.revision})
    if request.method == "POST" and form.is_valid():
        def remove(locked_period):
            obj = get_object_or_404(scoped_objects(locked_period, kind), pk=item)
            if kind == "offer" and obj.classroom_id:
                raise ValidationError("Uma oferta publicada preserva seu histórico e não pode ser excluída.")
            obj.delete()
            validate_existing(locked_period)
        try:
            mutate(request.user, pk, form.cleaned_data["revision"], remove)
            messages.success(request, "Registro removido do planejamento.")
            return redirect("planning:detail", pk=pk)
        except ERRORS as exc:
            form.add_error(None, error_text(exc))
    return render(request, "planning/delete.html", {"period": period, "object": instance, "form": form})


@login_required
@never_cache
@require_POST
def action(request, pk, action):
    period = get_period(request.user, pk)
    form = BatchForm(request.POST) if action == "import" else RevisionForm(request.POST)
    if not form.is_valid():
        return render(request, "planning/form.html", {"period": period, "form": form,
            "title": "Corrigir dados da operação"}, status=400)
    callbacks = {
        "import": lambda p: import_students(p, form.cleaned_data["students"]),
        "distribute": distribute, "schedule": generate_timetable,
        "publish": lambda p: publish(p, request.user),
    }
    if action not in callbacks:
        raise Http404
    try:
        result = mutate(request.user, pk, form.cleaned_data["revision"], callbacks[action])
        if action in ("distribute", "schedule"):
            messages.success(request, "Proposta gerada. Confira as pendências e ajuste os registros se necessário.")
            if result:
                messages.warning(request, f"{len(result)} pendência(s). A geração é uma sugestão e pode exigir ajustes manuais.")
        elif action == "import":
            messages.success(request, f"{result} alunos cadastrados na lista.")
        else:
            messages.success(request, "Turmas e vínculos publicados.")
            if result:
                messages.warning(request, f"{result} aluno(s) ainda sem acesso institucional ativo. "
                    "A lista escolar foi preservada; cadastre os acessos e publique novamente para vinculá-los.")
    except ERRORS as exc:
        messages.error(request, error_text(exc))
    return redirect("planning:detail", pk=pk)
