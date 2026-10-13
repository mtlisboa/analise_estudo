"""Role-aware navigation on every authenticated page."""
from django.urls import reverse
from features.users_manager.models import InstitutionalAccount


def sidebar_navigation(request):
    if not request.user.is_authenticated:
        return {}
    account = InstitutionalAccount.objects.filter(
        user=request.user, role__in=('ADMIN', 'MANAGER', 'STUDENT'),
        organization__is_active=True, organization__school__isnull=False,
    ).first()
    if not account:
        return {}
    match = request.resolver_match
    name = match.view_name if match else ''
    namespace = match.namespace if match else ''
    module = match.kwargs.get('module', '') if match else ''
    if account.role == 'STUDENT':
        return {'student_sidebar': True,
                'sidebar_student_home': name == 'institutions:aluno',
                'sidebar_student_disciplines': name in ('institutions:student-disciplines', 'institutions:student-discipline')}
    performance = name == 'institutions:manager-performance'
    if performance or namespace in ('planning', 'assessments', 'paper-exams'):
        module = 'academico'
    elif namespace == 'analytics-dashboard':
        module = 'analise'
    elif namespace == 'users-manager':
        module = 'administracao'
    elif namespace == 'organization-settings':
        module = 'institucional'
    return {'management_sidebar': True, 'sidebar_module': module,
            'sidebar_performance': performance,
            'sidebar_overview': name in ('institutions:gestor', 'accounts:dashboard'),
            'sidebar_can_plan': account.role == 'ADMIN'}
