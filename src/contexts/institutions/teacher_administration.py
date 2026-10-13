from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.paper_exams.models import SheetResult
from features.users_manager.models import Classroom
from features.users_manager.permissions import can_manage_classroom
from .coursework.services import teacher_disciplines
from .views import institutional_identity


@login_required
@never_cache
@require_GET
def index(request):
    account = institutional_identity(request.user)
    if account.role != 'TEACHER':
        raise PermissionDenied('Este módulo é exclusivo do professor.')
    classrooms = Classroom.objects.filter(organization=account.organization, is_active=True,
        memberships__user=request.user, memberships__role='TEACHER', memberships__status='ACTIVE').distinct()
    manageable = [c for c in classrooms.select_related('organization') if can_manage_classroom(request.user,c)]
    pending = SheetResult.objects.filter(status='review', sheet__run__created_by=request.user,
        sheet__run__assessment__owner=request.user, sheet__run__classroom__in=manageable
        ).select_related('sheet__run', 'sheet__student').order_by('pk')
    return render(request, 'institutions/teacher_administration.html', {
        'institution': account.organization.school, 'identity': account,
        'classrooms': classrooms, 'manageable_ids': [c.pk for c in manageable],
        'disciplines': teacher_disciplines(account), 'pending_reviews': pending[:10],
        'metrics': [('Minhas turmas', classrooms.count()),('Correções em revisão',pending.count())]})
