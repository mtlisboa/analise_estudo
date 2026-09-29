from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.accounts.institutional import can_provision
from features.users_manager.models import (
    Classroom, ClassroomTest, InstitutionalAccount, MembershipStatus,
)
from .roles import workspace_for


def institutional_identity(user):
    account = InstitutionalAccount.objects.select_related('organization__school').filter(
        user=user, organization__is_active=True,
        organization__school__isnull=False,
    ).first()
    if not account or not workspace_for(account):
        raise PermissionDenied('Esta área exige um acesso institucional ativo.')
    return account


@login_required
@never_cache
@require_GET
def index(request):
    account = institutional_identity(request.user)
    return redirect(f'institutions:{workspace_for(account).slug}')


@login_required
@never_cache
@require_GET
def workspace(request, slug):
    account = institutional_identity(request.user)
    context = workspace_for(account)
    if context.slug != slug:
        raise PermissionDenied('Seu perfil não tem acesso a este contexto.')

    organization = account.organization
    data = {'institution': organization.school, 'organization': organization,
            'identity': account, 'workspace': context, 'metrics': [], 'actions': []}
    classrooms = Classroom.objects.filter(organization=organization, is_active=True)
    if account.role in ('STUDENT', 'TEACHER'):
        classrooms = classrooms.filter(
            memberships__user=request.user, memberships__role=account.role,
            memberships__status=MembershipStatus.ACTIVE,
        ).distinct()
        tests = ClassroomTest.objects.filter(classroom__in=classrooms)
        if account.role == 'STUDENT':
            tests = tests.filter(is_published=True)
        data.update(classrooms=classrooms, tests=tests.select_related('classroom')[:20])
        from .planning.models import Offer
        itinerary = []
        published_offers = Offer.objects.filter(period__organization=organization,
            classroom__in=classrooms, period__published_at__isnull=False).select_related('period')
        for offer in published_offers:
            for lesson in offer.published_schedule:
                if account.role == 'TEACHER' and lesson['teacher_id'] != account.pk:
                    continue
                from datetime import date
                itinerary.append({**lesson, 'starts_on': date.fromisoformat(lesson['period_start']),
                    'ends_on': date.fromisoformat(lesson['period_end'])})
        data['itinerary'] = sorted(itinerary, key=lambda row: (row['starts_on'], row['day'], row['start'], row['classroom']))
        data['metrics'] = [('Minhas turmas', classrooms.count()), ('Atividades', tests.count())]
    elif account.role in ('ADMIN', 'MANAGER'):
        data['metrics'] = [
            ('Turmas ativas', classrooms.count()),
            ('Alunos', organization.institutional_accounts.filter(role='STUDENT').count()),
            ('Professores', organization.institutional_accounts.filter(role='TEACHER').count()),
        ]
        data['classrooms'] = classrooms
        # Only the existing administrator can provision identities. A manager
        # dashboard does not implicitly grant global or owner permissions.
        data['link_classrooms'] = account.role == 'ADMIN'
        if can_provision(request.user, organization):
            data['actions'] = [{
                'url': reverse('users-manager:institutional-accounts', args=[organization.pk]),
                'label': 'Gerenciar acessos',
            }, {
                'url': reverse('users-manager:organization-detail', args=[organization.pk]),
                'label': 'Gerenciar organização',
            }]
    elif account.role == 'OPERATOR':
        query = request.GET.get('q', '').strip()[:100]
        accounts = organization.institutional_accounts.select_related('user')
        if query:
            from django.db.models import Q
            accounts = accounts.filter(Q(registration__icontains=query) |
                Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query))
        from django.core.paginator import Paginator
        data.update(query=query, account_page=Paginator(accounts, 20).get_page(request.GET.get('page')))
    if account.role in ('ADMIN', 'OPERATOR'):
        data['actions'].append({'url': reverse('planning:index'), 'label': 'Montagem de turmas'})
    if account.role in ('STUDENT', 'TEACHER'):
        data['link_classrooms'] = True
    return render(request, f'institutions/{slug}.html', data)
