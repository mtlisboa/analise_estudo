"""Assessment applications are independent of assessment authoring."""
import uuid

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from features.assessments.models import Assessment
from features.paper_exams.services import issue_run
from ..planning.models import Offer
from .models import Publication
from .services import teacher_disciplines, publish
from .scheduling import execute_application
from .views import teacher_identity, base_data


class ApplicationForm(forms.Form):
    request_token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    kind = forms.ChoiceField(label='Tipo de aplicação', choices=[('EXAM', 'Prova'), ('ACTIVITY', 'Atividade')])
    offers = forms.ModelMultipleChoiceField(label='Turmas para aplicar', queryset=Offer.objects.none(), widget=forms.CheckboxSelectMultiple)
    title = forms.CharField(label='Título', max_length=160)
    delivery_mode = forms.ChoiceField(label='Formato de aplicação', choices=[('printed', 'Física'), ('online', 'Virtual')])
    instructions = forms.CharField(label='Instruções desta aplicação', required=False, max_length=3000, widget=forms.Textarea)
    scheduled_at = forms.DateTimeField(label='Aplicar em (horário local)', required=False, widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    is_visible = forms.BooleanField(label='Disponibilizar aos alunos', required=False, initial=True, help_text='Desmarcada: a aplicação virtual permanece oculta até você disponibilizá-la.')
    due_at = forms.DateTimeField(label='Aberta até', required=False, widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))

    def __init__(self, account, assessment, *args, scheduling=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheduling = scheduling
        ids = [r['offer'].pk for r in teacher_disciplines(account) if r['subject'].casefold() == assessment.subject.casefold()]
        self.fields['offers'].queryset = Offer.objects.filter(pk__in=ids)
        self.fields['title'].initial = assessment.topic
        self.fields['kind'].initial = assessment.kind
        self.fields['instructions'].initial = assessment.instructions
        self.fields['delivery_mode'].initial = 'online'
        self.fields['scheduled_at'].required = scheduling
        if scheduling:
            self.fields['is_visible'].label = 'Disponibilizar aos alunos no horário agendado'
        if not scheduling:
            del self.fields['scheduled_at']

    def clean(self):
        data = super().clean()
        start = data.get('scheduled_at') or timezone.now()
        if self.scheduling and start <= timezone.now():
            self.add_error('scheduled_at', 'Escolha uma data e horário futuros.')
        if data.get('delivery_mode') == 'printed':
            data['due_at'] = None
            data['is_visible'] = True
        if data.get('due_at') and data['due_at'] <= start:
            self.add_error('due_at', 'O prazo deve ser posterior ao início da aplicação.')
        if data.get('delivery_mode') == 'online' and not data.get('due_at'):
            self.add_error('due_at', 'Informe o prazo de entrega online.')
        return data


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def apply(request, assessment_pk, scheduling=False):
    account = teacher_identity(request)
    assessment = get_object_or_404(Assessment, pk=assessment_pk, owner=request.user)
    form = ApplicationForm(account, assessment, request.POST if request.method == 'POST' else None, scheduling=scheduling)
    if request.method == 'GET' and request.GET.get('delivery_mode') in ('online', 'printed'):
        form.initial['delivery_mode'] = request.GET['delivery_mode']
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                Assessment.objects.select_for_update().get(pk=assessment.pk)
                if not assessment.questions.exists():
                    raise ValidationError('Selecione as questões antes de aplicar a avaliação.')
                for offer in form.cleaned_data['offers']:
                    # A double click or repeated POST cannot issue a second application.
                    if Publication.objects.filter(request_token=form.cleaned_data['request_token'], offer=offer).exists():
                        continue
                    subject = next(r['subject'] for r in teacher_disciplines(account)
                        if r['offer'].pk == offer.pk and r['subject'].casefold() == assessment.subject.casefold())
                    obj = Publication(teacher=account, assessment=assessment, offer=offer, subject=subject,
                        request_token=form.cleaned_data['request_token'], application_status='scheduled',
                        scheduled_at=form.cleaned_data.get('scheduled_at') or timezone.now(),
                        release_visible=form.cleaned_data['is_visible'])
                    for key in ('kind', 'title', 'instructions', 'due_at', 'delivery_mode'):
                        setattr(obj, key, form.cleaned_data[key])
                    obj.save()
                    publish(account, obj, prepare_only=True)
                    if obj.delivery_mode == 'printed':
                        obj.exam_run = issue_run(assessment, offer.classroom, request.user)
                        obj.exam_run.title = obj.title
                        obj.exam_run.context.update(instructions=obj.instructions, description=assessment.description, content_topic=assessment.content_topic)
                        obj.exam_run.save(update_fields=['title', 'context'])
                        obj.save(update_fields=['exam_run'])
                    if not scheduling:
                        execute_application(obj.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Aplicação agendada com a configuração salva.' if scheduling else ('Aplicação realizada.' if form.cleaned_data['is_visible'] else 'Aplicação salva e oculta aos alunos.'))
            return redirect('coursework:apply', assessment_pk=assessment.pk)
    applications = Publication.objects.filter(assessment=assessment, teacher=account).select_related('offer', 'exam_run').order_by('-created_at')
    return render(request, 'coursework/apply.html', {**base_data(account), 'assessment': assessment, 'form': form,
        'scheduling': scheduling, 'applications': applications, 'application_timezone': timezone.get_current_timezone_name()})


@login_required
@require_POST
def cancel(request, pk):
    account = teacher_identity(request)
    with transaction.atomic():
        obj = get_object_or_404(Publication.objects.select_for_update(), pk=pk, teacher=account, assessment__owner=request.user)
        if obj.application_status in ('scheduled', 'failed'):
            obj.application_status = 'cancelled'
            obj.save(update_fields=['application_status'])
            messages.success(request, 'Agendamento cancelado.')
    return redirect('coursework:apply', assessment_pk=obj.assessment_id)


@login_required
@require_POST
def finalize(request, pk):
    account = teacher_identity(request)
    with transaction.atomic():
        obj = get_object_or_404(Publication.objects.select_for_update().select_related('offer__period'),
            pk=pk, teacher=account, delivery_mode='printed', application_status='completed')
        from .services import authorize_teacher
        authorize_teacher(account, obj.offer, obj.subject)
        if obj.finalized_at is None:
            obj.finalized_at = timezone.now()
            obj.save(update_fields=['finalized_at'])
        messages.success(request, 'Aplicação física finalizada. Gabaritos pendentes disponíveis em Correções.')
    return redirect('assessments:corrections')


@login_required
@require_POST
def make_visible(request, pk):
    account = teacher_identity(request)
    with transaction.atomic():
        obj = get_object_or_404(Publication.objects.select_for_update(), pk=pk, teacher=account,
            assessment__owner=request.user, delivery_mode='online', application_status='completed')
        if not obj.is_published:
            try:
                # Release exactly the saved application, never rebuild its questions.
                with transaction.atomic():
                    obj.release_visible = True
                    obj.application_status = 'scheduled'
                    obj.save(update_fields=['release_visible', 'application_status'])
                    execute_application(obj.pk)
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
            else:
                messages.success(request, 'Aplicação disponibilizada aos alunos.')
    return redirect('coursework:apply', assessment_pk=obj.assessment_id)
