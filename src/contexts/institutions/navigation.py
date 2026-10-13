"""Role-aware navigation on every authenticated page."""
from django.urls import reverse
from features.users_manager.models import InstitutionalAccount


def sidebar_navigation(request):
    if not request.user.is_authenticated:
        return {}
    account = InstitutionalAccount.objects.filter(
        user=request.user, role__in=('ADMIN', 'MANAGER', 'STUDENT', 'GUARDIAN', 'TEACHER'),
        organization__is_active=True, organization__school__isnull=False,
    ).first()
    match = request.resolver_match
    name = match.view_name if match else ''
    namespace = match.namespace if match else ''
    module = match.kwargs.get('module', '') if match else ''
    section = match.kwargs.get('section', '') if match else ''
    is_teacher = account and account.role == 'TEACHER'
    is_manager = account and account.role in ('ADMIN', 'MANAGER')
    bank_active = name == 'assessments:question-bank' or name.startswith('assessments:bank-question-')
    sharing_active = name == 'assessments:institutional-sharing'
    corrections_active = is_teacher and section == 'correcoes'
    evaluation_links = []
    if is_teacher:
        evaluation_links.append({'label': 'Provas e atividades', 'url': reverse('coursework:index'), 'active': namespace == 'coursework'})
    evaluation_links.extend([
        {'label': 'Editor de avaliações', 'url': reverse('assessments:index'),
         'active': namespace in ('assessments', 'paper-exams') and not bank_active and not sharing_active},
        {'label': 'Banco de questões', 'url': reverse('assessments:question-bank'), 'active': bank_active},
    ])
    if is_teacher:
        evaluation_links.extend([
            {'label': 'Disciplinas e publicações', 'url': reverse('institutions:teacher-administration-section', args=['publicacoes']),
             'active': section == 'publicacoes'},
            {'label': 'Correções pendentes', 'url': reverse('institutions:teacher-administration-section', args=['correcoes']),
             'active': corrections_active},
        ])
    if is_manager:
        evaluation_links.append({'label': 'Compartilhar questões', 'url': reverse('assessments:institutional-sharing'), 'active': sharing_active})
    evaluation_navigation = {'evaluation_links': evaluation_links,
        'evaluations_active': any(link['active'] for link in evaluation_links),
        'evaluation_section': bool(is_teacher and section in ('publicacoes', 'correcoes'))}
    if not account:
        return evaluation_navigation
    if name in ('institutions:classrooms', 'institutions:classroom'):
        module = 'academico'
    if account.role == 'TEACHER':
        return {'teacher_sidebar': True, **evaluation_navigation}
    if account.role == 'GUARDIAN':
        from .family.views import MODULES
        return {'family_sidebar': True, 'family_modules': MODULES,
                'family_active_module': module or ('inicio' if name == 'family:index' else '')}
    if account.role == 'STUDENT':
        return {'student_sidebar': True,
                'sidebar_student_home': name == 'institutions:aluno',
                'sidebar_student_disciplines': name in ('institutions:student-disciplines', 'institutions:student-discipline', 'coursework:student-detail')}
    performance = name == 'institutions:manager-performance'
    if performance or namespace == 'planning':
        module = 'academico'
    elif namespace in ('analytics-dashboard', 'institutions:institution-analysis'):
        module = 'analise'
    elif namespace == 'users-manager':
        module = 'administracao'
    elif namespace == 'organization-settings':
        module = 'institucional'
    return {**evaluation_navigation, 'management_sidebar': True, 'sidebar_module': module,
            'sidebar_performance': performance,
            'sidebar_overview': name in ('institutions:gestor', 'accounts:dashboard'),
            'sidebar_can_plan': account.role == 'ADMIN'}
