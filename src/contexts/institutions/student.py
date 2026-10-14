"""Student portal based exclusively on active enrolments and published schedules."""
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from features.users_manager.models import Classroom, MembershipStatus
from .planning.models import Offer
from .roles import workspace_for
from .views import institutional_identity


def enrolled_classrooms(account):
    return Classroom.objects.filter(
        organization=account.organization, is_active=True,
        memberships__user=account.user, memberships__role='STUDENT',
        memberships__status=MembershipStatus.ACTIVE,
    ).distinct()


def enrolled_subjects(account):
    subjects = []
    offers = Offer.objects.filter(
        period__organization=account.organization,
        period__published_at__isnull=False,
        classroom__in=enrolled_classrooms(account),
    ).select_related('period', 'classroom')
    for offer in offers:
        grouped = {}
        for lesson in offer.published_schedule:
            subject = grouped.setdefault(lesson['subject'], {
                'name': lesson['subject'], 'offer': offer, 'teachers': set(), 'itinerary': [],
            })
            subject['teachers'].add(lesson['teacher'])
            subject['itinerary'].append({**lesson,
                'starts_on': date.fromisoformat(lesson['period_start']),
                'ends_on': date.fromisoformat(lesson['period_end'])})
        for subject in grouped.values():
            subject['teachers'] = sorted(subject['teachers'])
            subject['itinerary'].sort(key=lambda row: (row['day'], row['start']))
            subjects.append(subject)
    return sorted(subjects, key=lambda row: (row['name'], -row['offer'].period.starts_on.toordinal(), row['offer'].name))


@login_required
@never_cache
@require_GET
def disciplines(request, code=None, subject=None):
    account = institutional_identity(request.user)
    if account.role != 'STUDENT':
        raise PermissionDenied('Esta área é exclusiva do aluno institucional.')
    subjects = enrolled_subjects(account)
    data = {'institution': account.organization.school, 'organization': account.organization,
            'identity': account, 'workspace': workspace_for(account), 'subjects': subjects}
    if code is not None:
        selected = next((row for row in subjects
                         if row['offer'].code == code and row['name'] == subject), None)
        if selected is None:
            raise Http404('Disciplina não encontrada nas suas matrículas.')
        from .coursework.services import student_publications
        from .coursework.models import PDFModule
        data.update(discipline=selected, itinerary=selected['itinerary'],
                    publications=student_publications(account, selected['offer'], subject),
                    pdf_modules=PDFModule.objects.filter(offer=selected['offer'], subject=subject).defer('document'))
        return render(request, 'institutions/student_discipline.html', data)
    query = request.GET.get('q', '').strip()[:100]
    data.update(query=query, subjects=[row for row in subjects if query.casefold() in row['name'].casefold()])
    return render(request, 'institutions/student_disciplines.html', data)
