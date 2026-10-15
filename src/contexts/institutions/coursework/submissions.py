from decimal import Decimal
import hashlib
import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import Publication, Submission, SubmissionReview
from .services import student_publications, enable_legacy_submission
from .views import base_data, owned_publication
from ..views import institutional_identity


def revision(publication):
    return hashlib.sha256(json.dumps(publication.public_snapshot, sort_keys=True).encode()).hexdigest()


class AnswerForm(forms.Form):
    revision = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, publication, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revision'].initial = revision(publication)
        for index, question in enumerate(publication.public_snapshot.get('questions', [])):
            name = f'q{index+1}'
            if question.get('type') == 'multiple_choice' or question.get('options'):
                self.fields[name] = forms.ChoiceField(label=f'Resposta da questão {index+1}',
                    choices=[(str(i), option) for i, option in enumerate(question['options'])], widget=forms.RadioSelect)
            else:
                self.fields[name] = forms.CharField(label=f'Resposta da questão {index+1}', max_length=15000,
                    widget=forms.Textarea(attrs={'rows': 5}))
        if not publication.public_snapshot.get('questions'):
            self.fields['response'] = forms.CharField(label='Sua resposta', max_length=15000, widget=forms.Textarea)


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def student_detail(request, pk):
    account = institutional_identity(request.user)
    if account.role != 'STUDENT':
        raise PermissionDenied
    obj = get_object_or_404(Publication.objects.select_related('offer__period'), pk=pk,
        offer__period__organization=account.organization)
    obj = get_object_or_404(student_publications(account, obj.offer, obj.subject), pk=pk)
    if request.method == 'POST' and obj.public_snapshot.get('delivery_mode') == 'printed':
        raise PermissionDenied('Este questionário é respondido em papel.')
    obj = enable_legacy_submission(obj)
    submission = Submission.objects.filter(publication=obj, student=request.user).first()
    form = AnswerForm(obj, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and not submission and form.is_valid():
        with transaction.atomic():
            obj = Publication.objects.select_for_update().get(pk=pk)
            # Repeat access checks after acquiring the publication lock.
            if not student_publications(account, obj.offer, obj.subject).filter(pk=pk).exists():
                raise PermissionDenied
            submission = Submission.objects.filter(publication=obj, student=request.user).first()
            if submission:
                return redirect('coursework:student-detail', pk=pk)
            if form.cleaned_data['revision'] != revision(obj):
                form.add_error(None, 'A atividade foi atualizada. Recarregue a página antes de responder.')
            elif obj.visible_due_at and timezone.now() > obj.visible_due_at:
                form.add_error(None, 'O prazo de envio desta atividade terminou.')
            elif len(obj.grading_snapshot) != len(obj.public_snapshot.get('questions', [])):
                form.add_error(None, 'O professor precisa republicar esta atividade para habilitar o envio.')
            else:
                answers = {k: v for k, v in form.cleaned_data.items() if k != 'revision'}
                score = Decimal('0')
                maximum = Decimal('0')
                pending = not obj.grading_snapshot
                for i, key in enumerate(obj.grading_snapshot):
                    maximum += Decimal(key['points'])
                    if key['type'] == 'open_ended' or key.get('manual'):
                        pending = True
                    elif obj.public_snapshot['questions'][i]['options'][int(answers[f'q{i+1}'])] == key['answer']:
                        score += Decimal(key['points'])
                Submission.objects.create(publication=obj, student=request.user, answers=answers,
                    automatic_score=score, maximum_score=maximum, score=None if pending else score)
                messages.success(request, 'Respostas enviadas. Sua entrega foi registrada.')
                return redirect('coursework:student-detail', pk=pk)
    rows = [(q, form[f'q{i+1}']) for i, q in enumerate(obj.public_snapshot.get('questions', []))]
    return render(request, 'coursework/student.html', {**base_data(account), 'publication': obj,
        'content': obj.public_snapshot, 'form': form, 'answer_rows': rows, 'submission': submission,
        'activity_started': request.GET.get('iniciar') == '1' or request.method == 'POST',
        'deadline_passed': bool(obj.visible_due_at and timezone.now() > obj.visible_due_at),
        'ready_for_submission': len(obj.grading_snapshot) == len(obj.public_snapshot.get('questions', []))})


class GradeForm(forms.Form):
    feedback = forms.CharField(label='Comentário da correção', required=False, max_length=5000, widget=forms.Textarea)

    def __init__(self, submission, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['feedback'].initial = submission.feedback
        for i, key in enumerate(submission.publication.grading_snapshot):
            if key['type'] == 'open_ended' or key.get('manual'):
                self.fields[f'q{i+1}'] = forms.DecimalField(label=f'Nota da questão {i+1} (máximo {key["points"]})',
                    min_value=0, max_value=Decimal(key['points']), decimal_places=2,
                    initial=submission.open_scores.get(f'q{i+1}'))


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def review(request, pk, submission_pk):
    account, publication = owned_publication(request, pk)
    submission = get_object_or_404(Submission, pk=submission_pk, publication=publication)
    form = GradeForm(submission, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            submission = Submission.objects.select_for_update().get(pk=submission.pk)
            scores = {k: str(v) for k, v in form.cleaned_data.items() if k != 'feedback'}
            SubmissionReview.objects.create(submission=submission, reviewer=request.user,
                previous_scores=submission.open_scores, scores=scores, feedback=form.cleaned_data['feedback'])
            submission.open_scores = scores
            submission.score = submission.automatic_score + sum((Decimal(v) for v in scores.values()), Decimal('0'))
            submission.feedback = form.cleaned_data['feedback']
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save()
        return redirect('coursework:edit', pk=pk)
    rows = [{'question': q, 'answer': submission.answers.get(f'q{i+1}', ''),
             'key': publication.grading_snapshot[i]} for i, q in enumerate(publication.public_snapshot.get('questions', []))]
    for row in rows:
        if row['question'].get('options'):
            row['answer'] = row['question']['options'][int(row['answer'])]
    return render(request, 'coursework/review.html', {**base_data(account), 'publication': publication,
        'submission': submission, 'rows': rows, 'form': form,
        'manual_grading': any(key.get('manual') for key in publication.grading_snapshot)})
