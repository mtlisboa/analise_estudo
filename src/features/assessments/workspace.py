"""Compact question bank and questionnaire workspace."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .bank_access import available_questions
from .models import Assessment, AssessmentTechnique, QuestionBankItem
from .services import add_bank_item_to_assessment
from contexts.institutions.coursework.models import Publication, Submission
from contexts.institutions.coursework.services import teacher_disciplines, publish, authorize_teacher
from contexts.institutions.planning.models import Offer
from features.paper_exams.models import ExamRun, SheetResult
from features.paper_exams.services import issue_run
from features.users_manager.models import InstitutionalAccount


def account_for(user):
    return InstitutionalAccount.objects.filter(user=user, role='TEACHER', organization__is_active=True).first()


def bank_rows(user, params):
    qs = available_questions(user).select_related('organization', 'owner')
    scope = params.get('scope', 'public')
    if scope == 'private':
        qs = qs.filter(owner=user, organization__isnull=True)
    elif scope != 'all':
        qs = qs.filter(organization__isnull=False)
    subject = params.get('subject', '').strip()[:120]
    if subject:
        qs = qs.filter(subject__iexact=subject)
    query = params.get('q', '').strip()[:150]
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(topic__icontains=query) | Q(subject__icontains=query) | Q(statement__icontains=query))
    before = params.get('before', '')
    if before.isdigit():
        qs = qs.filter(pk__lt=int(before))
    return qs.order_by('-pk')


@login_required
@never_cache
@require_GET
def bank(request):
    rows = list(bank_rows(request.user, request.GET)[:31])
    more = len(rows) > 30
    rows = rows[:30]
    data = {'questions': rows, 'selecting': request.GET.get('select') == '1'}
    if request.GET.get('fragment') == '1':
        return JsonResponse({'html': render_to_string('assessments/bank_rows.html', data, request=request),
            'next': rows[-1].pk if more else None})
    return render(request, 'assessments/bank_compact.html', {**data, 'scope': request.GET.get('scope', 'public'),
        'query': request.GET.get('q', ''), 'next_cursor': rows[-1].pk if more else '', 'workspace_page':'bank'})


@login_required
@never_cache
@require_GET
def preview(request, pk):
    question = get_object_or_404(available_questions(request.user).prefetch_related('images'), pk=pk)
    return render(request, 'assessments/question_preview.html', {'question': question})


class QuestionnaireForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(queryset=QuestionBankItem.objects.none(), required=False)
    offers = forms.ModelMultipleChoiceField(label='Turmas', queryset=Offer.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    instructions = forms.CharField(label='Instruções', required=False, max_length=3000, widget=forms.Textarea(attrs={'rows':3}))

    class Meta:
        model = Assessment
        fields = ['topic', 'subject', 'kind', 'delivery_mode', 'due_at', 'is_visible']
        labels = {'topic':'Título do questionário','subject':'Disciplina'}
        widgets = {'due_at': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type':'datetime-local'})}

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['kind'].required = False
        self.fields['due_at'].required = True
        self.fields['questions'].queryset = available_questions(user)
        self.account = account_for(user)
        self.courses = teacher_disciplines(self.account) if self.account else []
        self.fields['offers'].queryset = Offer.objects.filter(pk__in=[r['offer'].pk for r in self.courses]).select_related('period')
        if self.instance.pk:
            self.fields['questions'].initial = self.instance.questions.exclude(bank_item=None).values_list('bank_item_id', flat=True)
            self.fields['offers'].initial = Publication.objects.filter(assessment=self.instance, teacher=self.account).values_list('offer_id', flat=True) if self.account else []
            pub = Publication.objects.filter(assessment=self.instance).first()
            self.fields['instructions'].initial = pub.instructions if pub else ''

    def clean(self):
        data = super().clean()
        data['kind'] = data.get('kind') or (self.instance.kind if self.instance.pk else 'ACTIVITY')
        subject = data.get('subject','').strip().upper()
        data['subject'] = subject
        if any(item.subject.strip().upper() != subject for item in data.get('questions', [])):
            self.add_error('questions','Selecione questões da disciplina do questionário.')
        allowed = {r['offer'].pk for r in self.courses if r['subject'].casefold() == subject.casefold()}
        if any(o.pk not in allowed for o in data.get('offers', [])):
            self.add_error('offers','Selecione somente turmas em que você leciona essa disciplina.')
        if data.get('is_visible') and not data.get('offers'):
            self.add_error('offers','Selecione as turmas para disponibilizar o questionário.')
        if not data.get('questions') and not (self.instance.pk and self.instance.questions.filter(bank_item=None).exists()):
            self.add_error('questions','Selecione pelo menos uma questão.')
        return data


@login_required
@never_cache
@require_GET
def questionnaires(request):
    qs = Assessment.objects.filter(owner=request.user).annotate(question_total=Count('questions')).order_by('-updated_at')
    query = request.GET.get('q','').strip()[:100]
    if query:
        qs = qs.filter(Q(topic__icontains=query)|Q(subject__icontains=query))
    return render(request,'assessments/questionnaires.html',{'questionnaire_page':Paginator(qs,20).get_page(request.GET.get('page')),
        'query':query,'workspace_page':'questionnaires'})


@login_required
@never_cache
@require_http_methods(['GET','POST'])
def questionnaire(request, pk=None):
    identity = getattr(request.user, 'institutional_account', None)
    if identity and identity.role != 'TEACHER':
        raise PermissionDenied('Criação de questionários exclusiva do professor.')
    assessment = get_object_or_404(Assessment, pk=pk, owner=request.user) if pk else Assessment(owner=request.user)
    initial = {'subject': request.GET.get('subject','')}
    account = account_for(request.user)
    context_offer = request.GET.get('offer','')
    if not pk and account and context_offer.isdigit():
        rows = [r for r in teacher_disciplines(account) if r['offer'].pk == int(context_offer)
            and r['subject'].casefold() == initial['subject'].casefold()]
        if rows:
            initial.update(subject=rows[0]['subject'], offers=[int(context_offer)], is_visible=True)
    form = QuestionnaireForm(request.user, request.POST if request.method=='POST' else None, instance=assessment, initial=initial)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                if pk:
                    locked = Assessment.objects.select_for_update().get(pk=pk)
                    old_ids = set(locked.questions.exclude(bank_item=None).values_list('bank_item_id', flat=True))
                    new_ids = {q.pk for q in form.cleaned_data['questions']}
                    if (old_ids != new_ids or locked.delivery_mode != form.cleaned_data['delivery_mode'] or locked.subject != form.cleaned_data['subject']) and (
                            locked.examrun_set.exists() or Submission.objects.filter(publication__assessment=locked).exists()):
                        raise ValidationError('Este questionário já foi aplicado. Crie outro para alterar questões, disciplina ou formato.')
                obj = form.save(commit=False)
                if not obj.technique_id:
                    obj.technique = AssessmentTechnique.objects.order_by('pk').first()
                    if obj.technique is None:
                        obj.technique = AssessmentTechnique.objects.create(code='manual', name='Manual')
                obj.assembly_method = 'manual'
                obj.save()
                selected_ids = {q.pk for q in form.cleaned_data['questions']}
                obj.questions.filter(bank_item__isnull=False).exclude(bank_item_id__in=selected_ids).delete()
                for item in form.cleaned_data['questions']:
                    add_bank_item_to_assessment(obj,item)
                obj.assembly_status = 'ready'
                obj.save(update_fields=['assembly_status'])
                offers = list(form.cleaned_data['offers'])
                pubs = Publication.objects.filter(assessment=obj, teacher=form.account) if form.account else Publication.objects.none()
                pubs.exclude(offer__in=offers).update(is_published=False)
                if form.account:
                    for offer in offers:
                        subject = next(r['subject'] for r in form.courses if r['offer'].pk==offer.pk and r['subject'].casefold()==obj.subject.casefold())
                        pub = pubs.filter(offer=offer,subject=subject).order_by('pk').first() or Publication(teacher=form.account,offer=offer,subject=subject,assessment=obj)
                        pub.title = obj.topic
                        pub.instructions = form.cleaned_data['instructions']
                        pub.due_at = obj.due_at
                        pub.kind = obj.kind
                        pub.save()
                        if obj.is_visible:
                            publish(form.account,pub)
                            if obj.delivery_mode=='printed' and not ExamRun.objects.filter(assessment=obj,classroom=offer.classroom,created_by=request.user).exists():
                                issue_run(obj,offer.classroom,request.user)
                        else:
                            pub.is_published=False
                            pub.save(update_fields=['is_published'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request,'Questionário salvo. A visibilidade foi aplicada às turmas selecionadas.')
            return redirect('assessments:questionnaire-edit',pk=obj.pk)
    selected = list(form.fields['questions'].queryset.filter(pk__in=request.POST.getlist('questions'))) if request.method=='POST' else (
        list(form.fields['questions'].queryset.filter(pk__in=assessment.questions.values_list('bank_item_id',flat=True))) if pk else [])
    return render(request,'assessments/questionnaire_form.html',{'form':form,'assessment':assessment,'selected_questions':selected,
        'legacy_questions':assessment.questions.filter(bank_item=None) if pk else [],
        'runs':ExamRun.objects.filter(assessment=assessment,created_by=request.user) if pk else [],'workspace_page':'questionnaires'})


@login_required
@require_POST
def finalize(request, pk):
    obj=get_object_or_404(Assessment,pk=pk,owner=request.user,delivery_mode='printed')
    if not obj.examrun_set.filter(created_by=request.user).exists():
        messages.error(request,'Emita a prova para uma turma antes de finalizar a aplicação.')
    else:
        from features.paper_exams.views import permitted_run
        for run in obj.examrun_set.filter(created_by=request.user):
            permitted_run(request.user, run.pk)
        obj.is_finalized=True
        obj.save(update_fields=['is_finalized'])
        messages.success(request,'Aplicação finalizada. Os gabaritos pendentes estão em Correções.')
    return redirect('assessments:corrections')


@login_required
@never_cache
@require_GET
def corrections(request):
    account=account_for(request.user)
    if account is None:
        raise PermissionDenied('Área de correção exclusiva do professor institucional.')
    courses=teacher_disciplines(account)
    classroom = request.GET.get('classroom', '')
    if classroom.isdigit():
        courses = [r for r in courses if r['offer'].classroom_id == int(classroom)]
    query=Q(pk__in=[])
    rooms=[]
    for row in courses:
        query |= Q(publication__offer=row['offer'],publication__subject=row['subject'])
        rooms.append(row['offer'].classroom_id)
    online=Submission.objects.filter(query, publication__teacher=account,score__isnull=True).select_related('student','publication')
    runs=ExamRun.objects.filter(created_by=request.user,classroom_id__in=rooms)
    # Revalidate both classroom and discipline, rather than trusting historical membership.
    pairs={(r['offer'].classroom_id,r['subject'].casefold()) for r in courses}
    run_ids=[r.pk for r in runs if (r.classroom_id,(r.subject or r.assessment.subject).casefold()) in pairs]
    physical=SheetResult.objects.filter(sheet__run_id__in=run_ids,status='review').select_related('sheet__run')
    waiting=[]
    for run in runs.filter(pk__in=run_ids).filter(Q(assessment__is_finalized=True)|Q(assessment__due_at__lt=timezone.now())).select_related('assessment'):
        missing=run.sheets.filter(result__isnull=True).count()
        if missing:
            waiting.append({'run':run,'missing':missing})
    return render(request,'assessments/corrections.html',{'online':Paginator(online.order_by('submitted_at'),20).get_page(request.GET.get('online_page')),
        'physical':Paginator(physical.order_by('pk'),20).get_page(request.GET.get('physical_page')),
        'waiting':Paginator(waiting,20).get_page(request.GET.get('waiting_page')),'workspace_page':'corrections',
        'current_classroom':classroom if classroom.isdigit() else ''})
