from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    AddBankQuestionsForm,
    AIEditQuestionForm,
    AIGenerateQuestionForm,
    AssessmentForm,
    QuestionBankItemForm,
    QuestionForm,
)
from .models import Assessment, AssessmentType, QuestionBankItem
from .services import (
    add_bank_item_to_assessment,
    assemble_assessment,
    edit_question_with_ai,
    generate_question_with_ai,
)


def _assessment_queryset(user, query=""):
    assessments = Assessment.objects.filter(owner=user).prefetch_related(
        "assessment_types", "questions"
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
            | Q(questions__statement__icontains=query)
        )
    return assessments.distinct()


def _render_index(
    request,
    *,
    form=None,
    editing=None,
    question_form=None,
    question_assessment=None,
    status=200,
):
    query = request.GET.get("q", "").strip()
    assessment_types = AssessmentType.objects.select_related("default_technique")
    return render(
        request,
        "assessments/index.html",
        {
            "assessments": _assessment_queryset(request.user, query),
            "assessment_form": form or AssessmentForm(),
            "editing_assessment": editing,
            "question_form": question_form or QuestionForm(),
            "question_assessment": question_assessment,
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
        assessment = form.save(owner=request.user)
        try:
            assemble_assessment(assessment)
            messages.success(request, "Avaliação registrada e montada com sucesso.")
        except Exception:
            messages.warning(
                request,
                "A avaliação foi salva, mas a montagem não foi concluída. Consulte o motivo no card.",
            )
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


@login_required
def create_question(request: HttpRequest, assessment_pk: int) -> HttpResponse:
    assessment = get_object_or_404(
        Assessment,
        pk=assessment_pk,
        owner=request.user,
    )
    if request.method != "POST":
        return redirect("assessments:index")
    form = QuestionForm(request.POST)
    if form.is_valid():
        form.save(assessment=assessment)
        messages.success(request, "Questão adicionada à avaliação.")
        return redirect("assessments:index")
    return _render_index(
        request,
        question_form=form,
        question_assessment=assessment,
        status=422,
    )


@login_required
def question_bank(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    questions = QuestionBankItem.objects.filter(owner=request.user, is_active=True)
    if query:
        questions = questions.filter(
            Q(subject__icontains=query)
            | Q(topic__icontains=query)
            | Q(statement__icontains=query)
        )
    return render(
        request,
        "assessments/question_bank.html",
        {
            "questions": questions,
            "assessments": Assessment.objects.filter(owner=request.user),
            "selection_form": AddBankQuestionsForm(owner=request.user),
            "query": query,
        },
    )


def _question_initial(source):
    return {
        "subject": source.subject,
        "topic": source.topic,
        "question_type": source.question_type,
        "statement": source.statement,
        "options": "\n".join(source.options),
        "correct_answer": source.correct_answer,
        "explanation": source.explanation,
        "default_points": source.default_points,
    }


@login_required
def create_bank_question(request: HttpRequest, source_pk: int | None = None) -> HttpResponse:
    source = None
    if source_pk is not None:
        source = get_object_or_404(QuestionBankItem, pk=source_pk, owner=request.user)
    form = QuestionBankItemForm(
        request.POST or None,
        initial=_question_initial(source) if source and request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user, source=source)
        messages.success(
            request,
            "Nova versão adicionada ao banco." if source else "Questão adicionada ao banco.",
        )
        return redirect("assessments:question-bank")
    return render(
        request,
        "assessments/question_bank_form.html",
        {
            "form": form,
            "title": "Editar uma cópia existente" if source else "Criar questão manualmente",
            "description": (
                "A questão original será preservada e esta versão manterá o vínculo de origem."
                if source
                else "Crie um item reutilizável em diferentes atividades e provas."
            ),
        },
    )


@login_required
def update_bank_question(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(QuestionBankItem, pk=pk, owner=request.user)
    form = QuestionBankItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user)
        messages.success(request, "Questão atualizada no banco.")
        return redirect("assessments:question-bank")
    return render(
        request,
        "assessments/question_bank_form.html",
        {
            "form": form,
            "title": "Editar questão",
            "description": "A alteração afeta o banco; cópias já usadas em provas permanecem iguais.",
        },
    )


@login_required
def generate_bank_question_with_ai(request: HttpRequest) -> HttpResponse:
    form = AIGenerateQuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            generate_question_with_ai(
                request.user,
                form.cleaned_data["subject"],
                form.cleaned_data["topic"],
                form.cleaned_data["instructions"],
            )
        except Exception as exc:
            form.add_error(None, f"Não foi possível gerar a questão: {exc}")
        else:
            messages.success(request, "Questão gerada pela IA e adicionada ao banco.")
            return redirect("assessments:question-bank")
    return render(
        request,
        "assessments/question_ai_form.html",
        {"form": form, "title": "Gerar uma questão nova com IA"},
    )


@login_required
def edit_bank_question_with_ai(request: HttpRequest, pk: int) -> HttpResponse:
    source = get_object_or_404(QuestionBankItem, pk=pk, owner=request.user)
    form = AIEditQuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            edit_question_with_ai(source, form.cleaned_data["instructions"])
        except Exception as exc:
            form.add_error(None, f"Não foi possível editar a questão: {exc}")
        else:
            messages.success(request, "A versão editada pela IA foi adicionada ao banco.")
            return redirect("assessments:question-bank")
    return render(
        request,
        "assessments/question_ai_form.html",
        {
            "form": form,
            "title": "Solicitar edição via IA",
            "source": source,
        },
    )


@login_required
def add_bank_questions(request: HttpRequest, assessment_pk: int | None = None) -> HttpResponse:
    if request.method != "POST":
        return redirect("assessments:question-bank")
    form = AddBankQuestionsForm(request.POST, owner=request.user)
    if form.is_valid():
        assessment = form.cleaned_data["assessment"]
        if assessment_pk is not None and assessment.pk != assessment_pk:
            return redirect("assessments:question-bank")
        added = 0
        for item in form.cleaned_data["questions"]:
            before = assessment.questions.count()
            add_bank_item_to_assessment(assessment, item)
            added += assessment.questions.count() > before
        assessment.assembly_status = Assessment.AssemblyStatus.READY
        assessment.assembly_notes = f"{added} questão(ões) adicionada(s) manualmente do banco."
        assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
        messages.success(request, f"{added} questão(ões) adicionada(s) à avaliação.")
    return redirect("assessments:question-bank")
