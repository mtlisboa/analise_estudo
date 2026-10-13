from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from features.notifications.services import notify_user
from features.users_manager.models import InstitutionalAccount
from ..planning.models import Offer
from ..student import enrolled_classrooms
from .models import Publication


def teacher_disciplines(account):
    offers = Offer.objects.filter(period__organization=account.organization, classroom__organization=account.organization,
        period__published_at__isnull=False, classroom__is_active=True,
        classroom__memberships__user=account.user, classroom__memberships__role='TEACHER',
        classroom__memberships__status='ACTIVE').select_related('period', 'classroom').distinct()
    rows = []
    for offer in offers:
        names = {lesson['subject'] for lesson in offer.published_schedule if lesson['teacher_id'] == account.pk}
        rows.extend({'offer': offer, 'subject': subject} for subject in sorted(names))
    return rows


def authorize_teacher(account, offer, subject):
    if account.role != 'TEACHER' or not any(row['offer'].pk == offer.pk and row['subject'] == subject
            for row in teacher_disciplines(account)):
        raise PermissionDenied('Você não leciona esta disciplina na oferta publicada.')


def student_publications(account, offer, subject):
    if account.role != 'STUDENT' or not enrolled_classrooms(account).filter(pk=offer.classroom_id).exists():
        return Publication.objects.none()
    if not any(lesson['subject'] == subject for lesson in offer.published_schedule) or offer.period.published_at is None:
        return Publication.objects.none()
    return Publication.objects.filter(offer=offer, subject=subject, is_published=True).select_related('teacher__user')


@transaction.atomic
def publish(account, publication):
    publication = Publication.objects.select_for_update().select_related('offer__period', 'assessment').get(pk=publication.pk)
    authorize_teacher(account, publication.offer, publication.subject)
    if publication.teacher_id != account.pk or publication.assessment.owner_id != account.user_id:
        raise PermissionDenied
    questions = list(publication.assessment.questions.prefetch_related('images'))
    if not questions and (publication.kind == 'EXAM' or not publication.instructions.strip()):
        raise ValidationError('Uma prova precisa de questões. Uma atividade precisa de questões ou instruções.')
    for question in questions:
        question.full_clean()
    # Only these public fields cross into the student-facing snapshot.
    snapshot = {'title': publication.title, 'kind_label': publication.get_kind_display(),
        'instructions': publication.instructions, 'due_at': publication.due_at.isoformat() if publication.due_at else None,
        'questions': [{'support_text': q.support_text, 'images': [{'id': image.pk, 'description': image.description} for image in q.images.all()], 'statement': q.statement, 'question_type': q.get_question_type_display(),
                       'options': q.options, 'points': str(q.points)} for q in questions]}
    if publication.is_published and publication.public_snapshot == snapshot:
        return publication
    publication.public_snapshot = snapshot
    publication.is_published = True
    publication.published_at = timezone.now()
    publication.save(update_fields=['public_snapshot', 'is_published', 'published_at', 'updated_at'])
    recipients = InstitutionalAccount.objects.filter(organization=account.organization, role='STUDENT', user__is_active=True,
        user__classroom_memberships__classroom_id=publication.offer.classroom_id,
        user__classroom_memberships__role='STUDENT', user__classroom_memberships__status='ACTIVE').select_related('user').distinct()
    for recipient in recipients:
        notify_user(recipient=recipient.user, title=f'{publication.get_kind_display()} publicada',
            message=f'{publication.subject} · {publication.title} · {publication.offer.name}')
    return publication
