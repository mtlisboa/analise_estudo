from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .bank_access import managed_organizations
from .models import QuestionBankItem


class ExternalSharingForm(forms.Form):
    external_visibility = forms.ChoiceField(label='Disponibilidade', choices=QuestionBankItem.Visibility.choices)


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def institutional_sharing(request):
    organizations = managed_organizations(request.user)
    if not organizations.exists():
        raise PermissionDenied('Somente a gestão institucional pode liberar questões externamente.')
    questions = QuestionBankItem.objects.filter(organization__in=organizations, is_active=True)
    if request.method == 'POST':
        form = ExternalSharingForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item = get_object_or_404(questions.select_for_update(), pk=request.POST.get('question_id') if str(request.POST.get('question_id', '')).isdigit() else 0)
                item.external_visibility = form.cleaned_data['external_visibility']
                external = item.external_visibility != QuestionBankItem.Visibility.INSTITUTION
                item.sharing_approved_by = request.user if external else None
                item.sharing_approved_at = timezone.now() if external else None
                item.save(update_fields=['external_visibility', 'sharing_approved_by', 'sharing_approved_at', 'updated_at'])
            messages.success(request, 'Disponibilidade da questão atualizada.')
            return redirect('assessments:institutional-sharing')
        messages.error(request, 'Escolha uma disponibilidade válida.')
    query = request.GET.get('q', '').strip()[:200]
    if query:
        questions = questions.filter(Q(statement__icontains=query) | Q(subject__icontains=query) | Q(topic__icontains=query))
    return render(request, 'assessments/institutional_sharing.html', {
        'questions': Paginator(questions.select_related('organization', 'owner', 'sharing_approved_by').prefetch_related('images'), 25).get_page(request.GET.get('page')),
        'visibility_choices': QuestionBankItem.Visibility.choices, 'query': query,
    }, status=422 if request.method == 'POST' else 200)
