from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from features.assessments.forms import AssessmentForm, QuestionForm
from features.assessments.services import assemble_assessment
from ..planning.models import Offer
from ..roles import workspace_for
from ..views import institutional_identity
from .forms import ExistingAssessmentForm, PublicationForm
from .models import Publication
from .services import authorize_teacher, publish, teacher_disciplines


def teacher_identity(request):
    account = institutional_identity(request.user)
    if account.role != 'TEACHER':
        raise PermissionDenied('Área exclusiva do professor institucional.')
    return account


def base_data(account):
    return {'identity': account, 'organization': account.organization, 'institution': account.organization.school,
            'workspace': workspace_for(account)}


def owned_publication(request, pk):
    account = teacher_identity(request)
    obj = get_object_or_404(Publication.objects.select_related('offer__period', 'assessment'), pk=pk,
        teacher=account, offer__period__organization=account.organization)
    authorize_teacher(account, obj.offer, obj.subject)
    return account, obj


@login_required
@never_cache
@require_GET
def index(request):
    account = teacher_identity(request)
    courses = teacher_disciplines(account)
    rows = Publication.objects.filter(teacher=account, offer__period__organization=account.organization).select_related('offer__period')
    allowed = {(row['offer'].pk, row['subject']) for row in courses}
    rows = [row for row in rows if (row.offer_id, row.subject) in allowed]
    return render(request, 'coursework/index.html', {**base_data(account), 'courses': courses,
        'publication_page': Paginator(rows, 20).get_page(request.GET.get('page'))})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def create(request, code, subject):
    account = teacher_identity(request)
    offer = get_object_or_404(Offer.objects.select_related('period'), code=code, period__organization=account.organization)
    authorize_teacher(account, offer, subject)
    obj = Publication(offer=offer, subject=subject, teacher=account)
    data = request.POST if request.method == 'POST' else None
    publication_form = PublicationForm(data, instance=obj)
    use_existing = (request.POST.get('mode') if request.method == 'POST' else request.GET.get('mode')) == 'existing'
    existing = ExistingAssessmentForm(data if use_existing else None, account=account, subject=subject)
    assessment_data = request.POST.copy() if data is not None else None
    if assessment_data is not None:
        assessment_data['subject'] = subject
    assessment_form = AssessmentForm(assessment_data if not use_existing else None, initial={'subject': subject})
    assessment_form.fields['subject'].widget.attrs['readonly'] = True
    if request.method == 'POST' and publication_form.is_valid():
        valid = existing.is_valid() if use_existing else assessment_form.is_valid()
        if valid:
            with transaction.atomic():
                obj.assessment = existing.cleaned_data['assessment'] if use_existing else assessment_form.save(owner=account.user)
                obj.save()
                if not use_existing:
                    try:
                        assemble_assessment(obj.assessment)
                    except Exception:
                        messages.warning(request, 'Rascunho salvo. A montagem automática não foi concluída; adicione questões manualmente ou use o editor de avaliações.')
            return redirect('coursework:edit', pk=obj.pk)
    return render(request, 'coursework/create.html', {**base_data(account), 'offer': offer, 'subject': subject,
        'publication_form': publication_form, 'assessment_form': assessment_form, 'existing_form': existing,
        'mode': 'existing' if use_existing else 'new'})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def edit(request, pk):
    account, obj = owned_publication(request, pk)
    form = PublicationForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('coursework:edit', pk=pk)
    return render(request, 'coursework/edit.html', {**base_data(account), 'publication': obj, 'form': form,
        'question_form': QuestionForm(), 'questions': obj.assessment.questions.prefetch_related('images')})


@login_required
@never_cache
@require_POST
def add_question(request, pk):
    account, obj = owned_publication(request, pk)
    form = QuestionForm(request.POST, request.FILES)
    if form.is_valid():
        form.save(assessment=obj.assessment)
        return redirect('coursework:edit', pk=pk)
    return render(request, 'coursework/edit.html', {**base_data(account), 'publication': obj,
        'form': PublicationForm(instance=obj), 'question_form': form, 'questions': obj.assessment.questions.prefetch_related('images')}, status=422)


@login_required
@never_cache
@require_POST
def action(request, pk, operation):
    account, obj = owned_publication(request, pk)
    if operation == 'publish':
        try:
            publish(account, obj)
            messages.success(request, 'Publicação disponível na disciplina dos alunos matriculados.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    elif operation == 'withdraw':
        obj.is_published = False
        obj.save(update_fields=['is_published', 'updated_at'])
        messages.success(request, 'Publicação retirada da área dos alunos.')
    else:
        raise Http404
    return redirect('coursework:edit', pk=pk)


@login_required
@never_cache
@require_POST
def remove_question(request, pk, question_pk):
    account, obj = owned_publication(request, pk)
    question = get_object_or_404(obj.assessment.questions, pk=question_pk)
    question.delete()
    return redirect('coursework:edit', pk=pk)
