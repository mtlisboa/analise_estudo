"""Institutional management modules, isolated from personal analytics."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, FloatField, Q, Value
from django.db.models.functions import Cast
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.accounts.institutional import can_provision
from features.paper_exams.models import SheetResult
from features.users_manager.models import Classroom, InstitutionalAccount

MODULES = (
    ('academico', 'Acadêmico', 'Turmas, organização do ensino e desempenho dos alunos.'),
    ('analise', 'Análise', 'Composição da instituição e distribuição das turmas.'),
    ('administracao', 'Administração', 'Pessoas, perfis e acessos institucionais.'),
    ('institucional', 'Institucional', 'Identificação, localização e dados da escola.'),
)


def render_module(request, account, module='inicio'):
    if account.role not in ('ADMIN', 'MANAGER'):
        raise PermissionDenied('Este contexto é exclusivo da gestão institucional.')
    if module not in {'inicio', 'desempenho', *(slug for slug, _, _ in MODULES)}:
        raise Http404
    organization = account.organization
    classrooms = Classroom.objects.filter(organization=organization, is_active=True)
    accounts = organization.institutional_accounts.select_related('user')
    counts = dict(accounts.values('role').annotate(total=Count('pk')).values_list('role', 'total'))
    data = {
        'institution': organization.school, 'organization': organization, 'identity': account,
        'module': module, 'active_module': 'academico' if module == 'desempenho' else module,
        'modules': [{'slug': slug, 'title': title, 'description': description,
                     'url': reverse('institutions:manager-module', args=[slug])}
                    for slug, title, description in MODULES],
        'title': 'Gestão da instituição', 'description': 'Escolha um módulo para acompanhar a rotina da escola.',
        'metrics': [('Turmas ativas', classrooms.count()), ('Alunos cadastrados', counts.get('STUDENT', 0)),
                    ('Professores cadastrados', counts.get('TEACHER', 0))],
        'actions': [],
    }
    for slug, title, description in MODULES:
        if module == slug:
            data.update(title=title, description=description)
    if module == 'academico':
        data['classroom_page'] = Paginator(classrooms, 20).get_page(request.GET.get('page'))
        data['link_classrooms'] = account.role == 'ADMIN'
        if account.role == 'ADMIN':
            data['actions'].append({'url': reverse('planning:index'), 'label': 'Montagem de turmas'})
    elif module == 'desempenho':
        data.update(title='Desempenho', description='Resultados acadêmicos das provas corrigidas na instituição.')
        results = SheetResult.objects.filter(sheet__run__classroom__organization=organization)
        graded = results.filter(status=SheetResult.Status.GRADED, score__isnull=False, maximum_score__gt=0)
        percentage = Cast('score', FloatField()) * Value(100.0) / Cast('maximum_score', FloatField())
        average = graded.aggregate(value=Avg(percentage))['value']
        data['metrics'] = [('Provas corrigidas', graded.count()),
                           ('Aguardando revisão', results.filter(status=SheetResult.Status.REVIEW).count()),
                           ('Aproveitamento médio', f'{average:.1f}%'.replace('.', ',') if average is not None else '—')]
        rows = graded.order_by().values('sheet__run__classroom_id', 'sheet__run__classroom__name').annotate(
            total=Count('pk'), average=Avg(percentage)).order_by('sheet__run__classroom__name')
        data['performance_page'] = Paginator(rows, 20).get_page(request.GET.get('page'))
    elif module == 'analise':
        shift_counts = dict(classrooms.order_by().values('shift').annotate(total=Count('pk')).values_list('shift', 'total'))
        data['shift_rows'] = [(label, shift_counts.get(value, 0)) for value, label in Classroom.Shift.choices]
        data['role_rows'] = [(label, counts.get(value, 0)) for value, label in InstitutionalAccount.Role.choices]
    elif module == 'administracao':
        query = request.GET.get('q', '').strip()[:100]
        if query:
            accounts = accounts.filter(Q(registration__icontains=query) | Q(user__first_name__icontains=query)
                                       | Q(user__last_name__icontains=query))
        data.update(query=query, account_page=Paginator(accounts, 20).get_page(request.GET.get('page')))
        if can_provision(request.user, organization):
            data['actions'].append({'url': reverse('users-manager:institutional-accounts', args=[organization.pk]),
                                    'label': 'Gerenciar acessos'})
    elif module == 'institucional' and can_provision(request.user, organization):
        data['actions'].append({'url': reverse('organization-settings:detail', args=[organization.pk]),
                                'label': 'Configurar organização'})
    return render(request, 'institutions/gestor.html', data)


@login_required
@never_cache
@require_GET
def module_view(request, module):
    from .views import institutional_identity
    return render_module(request, institutional_identity(request.user), module)
