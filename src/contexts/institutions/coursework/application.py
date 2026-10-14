from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from features.assessments.models import Assessment
from ..planning.models import Offer
from .models import Publication
from .services import teacher_disciplines, publish
from .views import teacher_identity, base_data


class ApplicationForm(forms.Form):
    offers = forms.ModelMultipleChoiceField(label='Turmas para aplicar', queryset=Offer.objects.none(), widget=forms.CheckboxSelectMultiple)
    kind = forms.ChoiceField(label='Tipo', choices=Publication.Kind.choices)
    title = forms.CharField(label='Título', max_length=160)
    instructions = forms.CharField(label='Instruções', required=False, max_length=3000, widget=forms.Textarea)
    due_at = forms.DateTimeField(label='Prazo de entrega', required=False, widget=forms.DateTimeInput(attrs={'type':'datetime-local'}))

    def __init__(self, account, assessment, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ids = [r['offer'].pk for r in teacher_disciplines(account) if r['subject'].casefold() == assessment.subject.casefold()]
        self.fields['offers'].queryset = Offer.objects.filter(pk__in=ids)
        self.fields['title'].initial = assessment.topic


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def apply(request, assessment_pk):
    account = teacher_identity(request)
    assessment = get_object_or_404(Assessment, pk=assessment_pk, owner=request.user)
    form = ApplicationForm(account, assessment, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                # Serialize repeated application requests for this assessment.
                Assessment.objects.select_for_update().get(pk=assessment.pk)
                if not assessment.questions.exists():
                    raise ValidationError('Selecione as questões antes de aplicar a avaliação.')
                for offer in form.cleaned_data['offers']:
                    subject = next(r['subject'] for r in teacher_disciplines(account)
                        if r['offer'].pk == offer.pk and r['subject'].casefold() == assessment.subject.casefold())
                    obj = Publication.objects.filter(teacher=account, assessment=assessment, offer=offer, subject=subject).order_by('pk').first()
                    if obj is None:
                        obj = Publication(teacher=account, assessment=assessment, offer=offer, subject=subject)
                    for key in ('kind', 'title', 'instructions', 'due_at'):
                        setattr(obj, key, form.cleaned_data[key])
                    obj.save()
                    publish(account, obj)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Avaliação aplicada nas turmas selecionadas. Os alunos foram notificados.')
            return redirect('coursework:index')
    return render(request, 'coursework/apply.html', {**base_data(account), 'assessment': assessment, 'form': form})
