import csv
import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from features.assessments.models import Assessment
from features.users_manager.models import Classroom
from features.users_manager.permissions import can_manage_classroom, visible_classrooms
from .documents import answer_sheets_pdf, exam_pdf, LETTERS
from .models import ExamRun, SheetResult, ResultReview
from .services import issue_run, process_upload, csv_template, grade
from .omr import ReadError


def permitted_run(user, pk):
    run = get_object_or_404(ExamRun.objects.select_related('classroom__organization', 'assessment'), pk=pk, created_by=user)
    if not can_manage_classroom(user, run.classroom):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Você não possui mais acesso de gestão à turma.')
    return run


class IssueForm(forms.Form):
    classroom = forms.ModelChoiceField(label='Turma', queryset=Classroom.objects.none())

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permitted = [c.pk for c in visible_classrooms(user).select_related('organization') if can_manage_classroom(user, c)]
        self.fields['classroom'].queryset = Classroom.objects.filter(pk__in=permitted)


class UploadForm(forms.Form):
    file = forms.FileField(label='Arquivo de respostas', widget=forms.ClearableFileInput(attrs={
        'accept': '.csv,.zip,.pdf,.png,.jpg,.jpeg'}))


class ReviewForm(forms.Form):
    note = forms.CharField(label='Motivo da revisão', widget=forms.Textarea(attrs={'rows': 2}), max_length=2000)

    def __init__(self, result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i, question in enumerate(result.sheet.run.questions):
            self.fields[f'q{i+1}'] = forms.ChoiceField(label=f'Questão {i+1}', required=True,
                choices=[('-', 'Em branco / inválida')] + [(l, l) for l in LETTERS[:len(question['options'])]],
                initial=result.answers[i] if result.answers[i] in LETTERS and result.answers[i] else '-')


@login_required
@require_http_methods(['GET', 'POST'])
def index(request, assessment_pk):
    assessment = get_object_or_404(Assessment, pk=assessment_pk, owner=request.user)
    form = IssueForm(request.user, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            run = issue_run(assessment, form.cleaned_data['classroom'], request.user)
            return redirect('paper-exams:detail', pk=run.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, 'paper_exams/index.html', {'assessment': assessment, 'form': form,
        'runs': ExamRun.objects.filter(assessment=assessment, created_by=request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def detail(request, pk):
    run = permitted_run(request.user, pk)
    form = UploadForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            batch = process_upload(run, request.user, form.cleaned_data['file'])
            messages.info(request, f'Lote processado: {batch.results.count()} folhas importadas; {len(batch.errors)} ocorrências. Consulte os resultados abaixo.')
            return redirect('paper-exams:detail', pk=run.pk)
        except ReadError as exc:
            form.add_error('file', str(exc))
    return render(request, 'paper_exams/detail.html', {'run': run, 'form': form,
        'sheets': run.sheets.select_related('result'), 'batches': run.imports.all()[:20]})


def download_response(data, content_type, filename):
    response = HttpResponse(data, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def download(request, pk, kind):
    run = permitted_run(request.user, pk)
    if kind == 'folhas':
        return download_response(answer_sheets_pdf(run), 'application/pdf', 'folhas-de-respostas.pdf')
    if kind == 'provas':
        return download_response(exam_pdf(run), 'application/pdf', 'provas.pdf')
    if kind == 'modelo':
        return download_response(csv_template(run), 'text/csv; charset=utf-8', 'modelo-respostas.csv')
    if kind == 'resultados':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['student_id', 'aluno', 'estado', 'nota', 'total'] + [f'q{i+1}' for i in range(len(run.questions))])
        for sheet in run.sheets.select_related('result'):
            result = getattr(sheet, 'result', None)
            name = sheet.student_name
            if name.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                name = "'" + name
            writer.writerow([sheet.student_id, name, result.get_status_display() if result else 'Não importado',
                             result.score if result and result.score is not None else '',
                             result.maximum_score if result else ''] + (result.answers if result else ['']*len(run.questions)))
        return download_response('\ufeff'+stream.getvalue(), 'text/csv; charset=utf-8', 'resultados.csv')
    from django.http import Http404
    raise Http404


@login_required
@require_http_methods(['GET', 'POST'])
def review(request, result_pk):
    result = get_object_or_404(SheetResult.objects.select_related('sheet__run'), pk=result_pk)
    run = permitted_run(request.user, result.sheet.run_id)
    form = ReviewForm(result, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            locked = SheetResult.objects.select_for_update().get(pk=result.pk)
            answers = [form.cleaned_data[f'q{i+1}'].replace('-', '') for i in range(len(run.questions))]
            ResultReview.objects.create(result=locked, reviewer=request.user,
                previous_answers=locked.answers, answers=answers, note=form.cleaned_data['note'])
            locked.answers = answers
            locked.score, locked.maximum_score = grade(run.questions, locked.answers)
            locked.status = 'graded'
            locked.reviewed_by = request.user
            locked.reviewed_at = timezone.now()
            locked.review_note = form.cleaned_data['note']
            locked.save()
        return redirect('paper-exams:detail', pk=run.pk)
    return render(request, 'paper_exams/review.html', {'result': result, 'run': run, 'form': form})


@login_required
@require_GET
def evidence(request, result_pk):
    result = get_object_or_404(SheetResult.objects.select_related('sheet__run'), pk=result_pk)
    permitted_run(request.user, result.sheet.run_id)
    if not result.evidence:
        from django.http import Http404
        raise Http404
    response = HttpResponse(bytes(result.evidence), content_type='image/png')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
