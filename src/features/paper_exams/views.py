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
from .models import ExamRun, SheetResult, ResultReview, AnswerSheet, ScanPage
from .services import issue_run, process_upload, csv_template, grade
from .omr import ReadError


def permitted_run(user, pk):
    run = get_object_or_404(ExamRun.objects.select_related('classroom__organization', 'assessment'), pk=pk, created_by=user)
    if not can_manage_classroom(user, run.classroom):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Você não possui mais acesso de gestão à turma.')
    account = getattr(user, 'institutional_account', None)
    if account:
        from contexts.institutions.coursework.services import teacher_offers
        if not teacher_offers(account).filter(classroom_id=run.classroom_id).exists():
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
    return run


class IssueForm(forms.Form):
    classroom = forms.ModelChoiceField(label='Turma', queryset=Classroom.objects.none())

    def __init__(self, user, *args, assessment=None, **kwargs):
        super().__init__(*args, **kwargs)
        permitted = [c.pk for c in visible_classrooms(user).select_related('organization') if can_manage_classroom(user, c)]
        account = getattr(user, 'institutional_account', None)
        if account and assessment:
            from contexts.institutions.coursework.services import teacher_offers
            permitted = list(teacher_offers(account).values_list('classroom_id', flat=True))
        self.fields['classroom'].queryset = Classroom.objects.filter(pk__in=permitted)


class UploadForm(forms.Form):
    file = forms.FileField(label='Arquivo de respostas', widget=forms.ClearableFileInput(attrs={
        'accept': '.csv,.zip,.pdf,.png,.jpg,.jpeg'}))


class ReviewForm(forms.Form):
    note = forms.CharField(label='Motivo da revisão', widget=forms.Textarea(attrs={'rows': 2}), max_length=2000)

    def __init__(self, result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i, question in enumerate(result.sheet.questions):
            if question.get('type') == 'open_ended':
                from decimal import Decimal
                self.fields[f'open{i+1}'] = forms.DecimalField(label=f'Questão {i+1}: {question["statement"]} — nota (máximo {question["points"]})',
                    min_value=0, max_value=Decimal(question['points']), decimal_places=2,
                    initial=result.open_scores.get(str(i+1)))
                continue
            self.fields[f'q{i+1}'] = forms.ChoiceField(label=f'Questão {i+1}', required=True,
                choices=[('-', 'Em branco / inválida')] + [(l, l) for l in LETTERS[:len(question['options'])]],
                initial=result.answers[i] if result.answers[i] in LETTERS and result.answers[i] else '-')


@login_required
@require_http_methods(['GET', 'POST'])
def index(request, assessment_pk):
    assessment = get_object_or_404(Assessment, pk=assessment_pk, owner=request.user)
    form = IssueForm(request.user, request.POST if request.method == 'POST' else None, assessment=assessment)
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


def download_response(data, content_type, filename, *, inline=False):
    response = HttpResponse(data, content_type=content_type)
    response['Content-Disposition'] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def download(request, pk, kind):
    run = permitted_run(request.user, pk)
    sheets = run.sheets.all()
    if request.GET.get('student'):
        sheet = get_object_or_404(sheets, student_id=request.GET['student'])
        sheets = [sheet]
    if kind == 'folhas':
        if run.context.get('omit_answer_sheet', False):
            return HttpResponse('Esta aplicação foi configurada sem folha de respostas. Reimprima o caderno de questões.', status=400)
        return download_response(answer_sheets_pdf(run, sheets), 'application/pdf', 'folhas-de-respostas.pdf', inline=request.GET.get('inline') == '1')
    if kind == 'provas':
        return download_response(exam_pdf(run, sheets, include_answer_sheet=not bool(request.GET.get('student'))), 'application/pdf', 'provas.pdf', inline=request.GET.get('inline') == '1')
    if kind == 'gabaritos' and run.variants:
        from .documents import variant_keys_pdf
        return download_response(variant_keys_pdf(run), 'application/pdf', 'gabaritos-ABC.pdf')
    if kind == 'modelo':
        return download_response(csv_template(run), 'text/csv; charset=utf-8', 'modelo-respostas.csv')
    if kind == 'resultados':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['student_id', 'aluno'] + (['versao'] if run.variants else []) + ['estado', 'nota', 'total'] + [f'q{i+1}' for i in range(len(run.questions))])
        for sheet in run.sheets.select_related('result'):
            result = getattr(sheet, 'result', None)
            name = sheet.student_name
            if name.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                name = "'" + name
            writer.writerow([sheet.student_id, name] + ([sheet.variant] if run.variants else []) + [result.get_status_display() if result else 'Não importado',
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
            answers = [locked.answers[i] if q.get('type') == 'open_ended' else form.cleaned_data[f'q{i+1}'].replace('-', '')
                       for i, q in enumerate(result.sheet.questions)]
            open_scores = {str(i+1): str(form.cleaned_data[f'open{i+1}']) for i, q in enumerate(result.sheet.questions)
                           if q.get('type') == 'open_ended'}
            ResultReview.objects.create(result=locked, reviewer=request.user,
                previous_answers=locked.answers, answers=answers, note=form.cleaned_data['note'],
                previous_open_scores=locked.open_scores, open_scores=open_scores)
            locked.answers = answers
            locked.open_scores = open_scores
            from contexts.institutions.analysis.services import effective_questions
            locked.score, locked.maximum_score = grade(effective_questions(run, result.sheet), locked.answers, open_scores)
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


class CameraForm(forms.Form):
    file = forms.ImageField(label='Fotografar página da prova', widget=forms.FileInput(attrs={
        'accept': 'image/jpeg,image/png', 'capture': 'environment'}))


@login_required
@require_http_methods(['GET', 'POST'])
def scan(request):
    from .omr import decode_image, page_identity
    from .services import MAX_UPLOAD
    form = CameraForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['file']
        try:
            if upload.size > MAX_UPLOAD:
                raise ReadError('A foto deve ter até 30 MB.')
            identity = page_identity(decode_image(upload.read(MAX_UPLOAD + 1)))
            if not identity:
                raise ReadError('QR code ilegível. Fotografe uma página inteira, com boa iluminação.')
            sheet = get_object_or_404(AnswerSheet, pk=identity['sheet'], student_id=identity['student'])
            run = permitted_run(request.user, sheet.run_id)
            upload.seek(0)
            batch = process_upload(run, request.user, upload)
            if batch.errors:
                for error in batch.errors:
                    form.add_error(None, error)
            else:
                messages.success(request, f'Página identificada e anexada a {sheet.student_name}, turma {run.classroom_name}.')
                return redirect('paper-exams:detail', pk=run.pk)
        except ReadError as exc:
            form.add_error(None, str(exc))
    return render(request, 'paper_exams/scan.html', {'form': form})


@login_required
@require_GET
def scan_evidence(request, page_pk):
    page = get_object_or_404(ScanPage.objects.select_related('sheet__run'), pk=page_pk)
    permitted_run(request.user, page.sheet.run_id)
    response = HttpResponse(bytes(page.evidence), content_type='image/png')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def print_application(request, request_token):
    """Open already persisted booklets for printing without issuing new sheets."""
    from contexts.institutions.coursework.models import Publication
    from pypdf import PdfReader, PdfWriter
    publications = list(Publication.objects.filter(request_token=request_token, teacher__user=request.user,
        delivery_mode='printed', exam_run__isnull=False).select_related('exam_run').order_by('offer_id'))
    if not publications:
        from django.http import Http404
        raise Http404
    from .documents import application_print_pdf
    runs = [permitted_run(request.user, publication.exam_run_id) for publication in publications]
    response = HttpResponse(application_print_pdf(runs), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="provas-para-impressao.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_GET
def students(request):
    """Teacher student area: reprint existing documents without issuing new sheets."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from contexts.institutions.coursework.views import teacher_identity, base_data
    from contexts.institutions.coursework.services import teacher_offers
    from features.users_manager.models import ClassroomMembership
    account = teacher_identity(request)
    classroom_ids = teacher_offers(account).values_list('classroom_id', flat=True)
    members = ClassroomMembership.objects.filter(classroom_id__in=classroom_ids,
        role='STUDENT', status='ACTIVE')
    allowed = get_user_model().objects.filter(pk__in=members.values('user_id'), is_active=True)
    query = request.GET.get('q', '').strip()[:100]
    found = allowed
    if query:
        found = found.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(username__icontains=query) | Q(institutional_account__registration__icontains=query))
    selected = None
    sheets = AnswerSheet.objects.none()
    if request.GET.get('student', '').isdigit():
        selected = get_object_or_404(allowed, pk=request.GET['student'])
        sheets = AnswerSheet.objects.filter(student=selected, run__created_by=request.user,
            run__classroom_id__in=classroom_ids).select_related('run').order_by('-run__created_at')
    return render(request, 'paper_exams/students.html', {
        **base_data(account), 'students': found.order_by('first_name', 'last_name', 'pk')[:50],
        'query': query, 'selected_student': selected, 'sheets': sheets})
