from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, FloatField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.paper_exams.models import SheetResult
from features.users_manager.models import Classroom, ClassroomMembership, InstitutionalAccount
from .views import institutional_identity


def active_classrooms(account):
    return Classroom.objects.filter(
        organization=account.organization, is_active=True,
        memberships__user_id=account.user_id, memberships__role=account.role,
        memberships__status='ACTIVE',
    )


def performance(classrooms, student_id=None):
    from .coursework.models import Submission

    paper = SheetResult.objects.filter(
        sheet__run__classroom__in=classrooms, status=SheetResult.Status.GRADED,
    )
    online = Submission.objects.filter(
        publication__offer__classroom__in=classrooms, publication__is_published=True,
    )
    if student_id is not None:
        paper = paper.filter(sheet__student_id=student_id)
        online = online.filter(student_id=student_id)

    totals = {}
    for results, classroom_field in (
        (paper, 'sheet__run__classroom_id'),
        (online, 'publication__offer__classroom_id'),
    ):
        rows = results.filter(score__isnull=False, maximum_score__gt=0).order_by().values(
            classroom_field,
        ).annotate(count=Count('pk'), average=Avg(Cast('score', FloatField()) * 100 / Cast('maximum_score', FloatField())))
        for row in rows:
            count, total = totals.get(row[classroom_field], (0, 0))
            totals[row[classroom_field]] = count + row['count'], total + row['average'] * row['count']

    for classroom_id, name in classrooms.order_by('name', 'pk').values_list('pk', 'name'):
        count, total = totals.get(classroom_id, (0, 0))
        yield {'name': name, 'count': count, 'average': total / count if count else None}


@login_required
@never_cache
@require_GET
def student_profile(request, classroom_id, membership_id):
    identity = institutional_identity(request.user)
    if identity.role not in ('TEACHER', 'MANAGER', 'ADMIN'):
        raise PermissionDenied
    classrooms = Classroom.objects.filter(organization=identity.organization, is_active=True)
    if identity.role == 'TEACHER':
        classrooms = active_classrooms(identity)
    classroom = get_object_or_404(classrooms, pk=classroom_id)
    student = get_object_or_404(
        ClassroomMembership.objects.select_related('user'),
        pk=membership_id, classroom=classroom, role='STUDENT', status='ACTIVE',
    )
    analysis = request.GET.get('tab') == 'analise'
    return render(request, 'institutions/student_profile.html', {
        'student_name': student.user.get_full_name() or 'Aluno',
        'classroom': classroom,
        'analysis_tab': analysis,
        'performance_rows': performance(classrooms.filter(pk=classroom.pk), student.user_id) if analysis else (),
    })
