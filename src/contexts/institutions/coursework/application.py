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
    virtual_shuffle_questions = forms.BooleanField(label='Embaralhar questões para cada aluno', required=False)
    virtual_shuffle_options = forms.BooleanField(label='Embaralhar alternativas para cada aluno', required=False)

    shuffle_questions = forms.BooleanField(label='Embaralhar questões', required=False, initial=True)
    shuffle_options = forms.BooleanField(label='Embaralhar alternativas', required=False, initial=True)

    request_token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    kind = forms.ChoiceField(label='Tipo de aplicação', choices=[('EXAM', 'Prova'), ('ACTIVITY', 'Atividade')])
    offers = forms.ModelMultipleChoiceField(label='Turmas para aplicar', queryset=Offer.objects.none(), widget=forms.CheckboxSelectMultiple)
    title = forms.CharField(label='Título', max_length=160)
    delivery_mode = forms.ChoiceField(choices=[('printed', 'Física'), ('online', 'Virtual')], widget=forms.HiddenInput)
    instructions = forms.CharField(label='Instruções desta aplicação', required=False, max_length=3000,
        help_text='Preenchido com as instruções do questionário. Você pode editar o texto para esta aplicação.',
        widget=forms.Textarea(attrs={'rows': 4}))
    scheduled_at = forms.DateTimeField(label='Data e hora de início da aplicação', required=False, help_text='Horário local. Deixe vazio para iniciar ao confirmar; uma data futura programa o início.', widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))
    is_visible = forms.BooleanField(label='Disponibilizar aos alunos', required=False, initial=True, help_text='Desmarcada: a aplicação virtual permanece oculta até você disponibilizá-la.')
    due_at = forms.DateTimeField(label='Aberta até', required=False, widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))

    def __init__(self, account, assessment, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = [r['offer'].pk for r in teacher_disciplines(account) if r['subject'].casefold() == assessment.subject.casefold()]
        self.fields['offers'].queryset = Offer.objects.filter(pk__in=ids).select_related('period', 'classroom')
        self.fields['offers'].label_from_instance = lambda offer: f'{offer.name} · {offer.grade} · {offer.get_shift_display()} · {offer.period.name}'
        self.fields['title'].initial = assessment.topic
        self.fields['kind'].initial = assessment.kind
        self.initial.setdefault('instructions', assessment.instructions or '')
        self.fields['delivery_mode'].initial = 'online'
        self.fields['is_visible'].label = 'Disponibilizar aos alunos no início da aplicação'

    def clean(self):
        data = super().clean()
        start = data.get('scheduled_at') or timezone.now()
        if data.get('scheduled_at') and start <= timezone.now():
            self.add_error('scheduled_at', 'Escolha uma data e horário futuros.')
        if data.get('delivery_mode') != 'online':
            data['virtual_shuffle_questions'] = False
            data['virtual_shuffle_options'] = False
        if data.get('delivery_mode') != 'printed' or data.get('kind') != 'EXAM':
            data['shuffle_questions'] = False
            data['shuffle_options'] = False
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
def apply(request, assessment_pk):
    account = teacher_identity(request)
    assessment = get_object_or_404(Assessment, pk=assessment_pk, owner=request.user)
    form = ApplicationForm(account, assessment, request.POST if request.method == 'POST' else None)
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
                        release_visible=form.cleaned_data['is_visible'],
                        application_metadata={
                            'virtual_shuffle_questions': form.cleaned_data['virtual_shuffle_questions'],
                            'virtual_shuffle_options': form.cleaned_data['virtual_shuffle_options'],
                            'physical_shuffle_questions': form.cleaned_data['shuffle_questions'],
                            'physical_shuffle_options': form.cleaned_data['shuffle_options'],
                            'assessment_metadata': list(assessment.metadata_tags),
                            'selected_offer_ids': [offer.pk for offer in form.cleaned_data['offers']],
                        })
                    for key in ('kind', 'title', 'instructions', 'due_at', 'delivery_mode'):
                        setattr(obj, key, form.cleaned_data[key])
                    obj.save()
                    publish(account, obj, prepare_only=True)
                    if obj.delivery_mode == 'printed':
                        obj.exam_run = issue_run(assessment, offer.classroom, request.user, versioned=obj.kind == 'EXAM',
                            shuffle_questions=form.cleaned_data['shuffle_questions'], shuffle_options=form.cleaned_data['shuffle_options'],
                            variant_seed=str(form.cleaned_data['request_token']))
                        obj.exam_run.title = obj.title
                        obj.exam_run.context.update(instructions=obj.instructions, description=assessment.description, content_topic=assessment.content_topic,
                            application_metadata=obj.application_metadata, application_id=obj.pk, kind=obj.kind,
                            starts_at=obj.scheduled_at.isoformat(), due_at=obj.due_at.isoformat() if obj.due_at else None)
                        obj.exam_run.save(update_fields=['title', 'context'])
                        obj.save(update_fields=['exam_run'])
                    if not form.cleaned_data.get('scheduled_at'):
                        execute_application(obj.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Aplicação salva para iniciar na data e hora definidas.' if form.cleaned_data.get('scheduled_at') else ('Aplicação realizada.' if form.cleaned_data['is_visible'] else 'Aplicação salva e oculta aos alunos.'))
            if form.cleaned_data['delivery_mode'] == 'printed':
                return redirect('paper-exams:print-application', request_token=form.cleaned_data['request_token'])
            return redirect('coursework:apply', assessment_pk=assessment.pk)
    applications = Publication.objects.filter(assessment=assessment, teacher=account).select_related('offer', 'exam_run').order_by('-created_at')
    return render(request, 'coursework/apply.html', {**base_data(account), 'assessment': assessment, 'form': form,
        'applications': applications, 'application_timezone': timezone.get_current_timezone_name()})


@login_required
@require_POST
def cancel(request, pk):
    account = teacher_identity(request)
    with transaction.atomic():
        obj = get_object_or_404(Publication.objects.select_for_update(), pk=pk, teacher=account, assessment__owner=request.user)
        if obj.application_status in ('scheduled', 'failed'):
            obj.application_status = 'cancelled'
            obj.save(update_fields=['application_status'])
            messages.success(request, 'Aplicação cancelada.')
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


@login_required
@require_http_methods(['GET', 'POST'])
def legacy_schedule(request, assessment_pk):
    """Old links enter the unified application flow."""
    if request.method == 'POST':
        return apply(request, assessment_pk)
    from django.urls import reverse
    url = reverse('coursework:apply', kwargs={'assessment_pk': assessment_pk})
    mode = request.GET.get('delivery_mode')
    if mode in ('online', 'printed'):
        url += '?delivery_mode=' + mode
    return redirect(url)
