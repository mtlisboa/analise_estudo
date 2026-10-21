from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

from features.notifications.services import notify_user
from features.users_manager.models import InstitutionalAccount
from ..planning.models import Offer
from ..student import enrolled_classrooms
from .models import Publication


def teacher_offers(account):
    """Application access follows the teacher's active classroom membership."""
    if account.role != 'TEACHER':
        return Offer.objects.none()
    return Offer.objects.filter(
        period__organization=account.organization,
        classroom__organization=account.organization,
        classroom__is_active=True,
        classroom__memberships__user=account.user,
        classroom__memberships__role='TEACHER',
        classroom__memberships__status='ACTIVE',
    ).select_related('period', 'classroom').distinct()


def teacher_disciplines(account):
    offers = Offer.objects.filter(period__organization=account.organization, classroom__organization=account.organization,
        period__published_at__isnull=False, classroom__is_active=True,
        classroom__memberships__user=account.user, classroom__memberships__role='TEACHER',
        classroom__memberships__status='ACTIVE').select_related('period', 'classroom').distinct()
    rows = []
    for offer in offers:
        names = {lesson['subject'] for lesson in offer.published_schedule if str(lesson.get('teacher_id')) == str(account.pk)}
        rows.extend({'offer': offer, 'subject': subject} for subject in sorted(names))
    return rows


def authorize_teacher(account, offer, subject):
    if not teacher_offers(account).filter(pk=offer.pk).exists():
        raise PermissionDenied('Você não possui vínculo ativo de professor nesta turma da instituição.')


def student_publications(account, offer, subject):
    if account.role != 'STUDENT' or not enrolled_classrooms(account).filter(pk=offer.classroom_id).exists():
        return Publication.objects.none()
    if not any(lesson['subject'] == subject for lesson in offer.published_schedule) or offer.period.published_at is None:
        return Publication.objects.none()
    return Publication.objects.filter(offer=offer, subject=subject, is_published=True).select_related('teacher__user')


@transaction.atomic
def publish(account, publication, *, prepare_only=False):
    publication = Publication.objects.select_for_update().select_related('offer__period', 'assessment').get(pk=publication.pk)
    authorize_teacher(account, publication.offer, publication.subject)
    if publication.teacher_id != account.pk or publication.assessment.owner_id != account.user_id:
        raise PermissionDenied
    if publication.application_status in ('cancelled', 'failed', 'completed') or (publication.application_status == 'scheduled' and not prepare_only):
        raise ValidationError('Use o fluxo de aplicações para esta avaliação agendada.')
    from features.assessments.application_scoring import application_question_order
    questions = application_question_order(list(publication.assessment.questions.prefetch_related('images')),
        publication.application_metadata.get('question_order'))
    if not questions and (publication.kind == 'EXAM' or not publication.instructions.strip()):
        raise ValidationError('Uma prova precisa de questões. Uma atividade precisa de questões ou instruções.')
    for question in questions:
        question.full_clean()
    from features.assessments.application_scoring import application_points
    points = application_points(questions, publication.application_metadata.get('question_points'))
    from .digital import option_ids
    # Only these public fields cross into the student-facing snapshot.
    from decimal import Decimal
    snapshot = {'total_points': str(sum((Decimal(value) for value in points.values()), Decimal('0'))), 'delivery_mode': (publication.delivery_mode or publication.assessment.delivery_mode), 'title': publication.title, 'kind_label': publication.get_kind_display(),
        'description': publication.assessment.description, 'content_topic': publication.assessment.content_topic,
        'instructions': publication.instructions, 'due_at': publication.due_at.isoformat() if publication.due_at else None,
        'questions': [{'id': str(q.pk), 'option_ids': option_ids(q), 'answer_lines': q.answer_lines, 'content_blocks': q.ordered_content, 'support_text': q.support_text, 'images': [{'id': image.pk, 'description': image.description} for image in q.images.all()], 'statement': q.statement, 'question_type': q.get_question_type_display(), 'type': q.question_type,
                       'options': q.options, 'points': points[str(q.pk)]} for q in questions]}
    grading = [{'question_id': str(q.pk), 'correct_option_id': option_ids(q)[q.options.index(q.correct_answer)] if q.question_type == 'multiple_choice' else None, 'type': q.question_type, 'answer': q.correct_answer, 'points': points[str(q.pk)]} for q in questions]
    if publication.public_snapshot == snapshot and publication.grading_snapshot == grading:
        if publication.is_published:
            return publication
    elif publication.submissions.exists():
        raise ValidationError('Esta publicação já recebeu respostas. Crie outra aplicação para alterar as questões ou o gabarito.')
    publication.grading_snapshot = grading
    publication.public_snapshot = snapshot
    if prepare_only:
        publication.save(update_fields=['public_snapshot', 'grading_snapshot', 'updated_at'])
        return publication
    return activate_publication(account, publication)


def activate_publication(account, publication):
    """Release the saved snapshot, without rebuilding a scheduled assessment."""
    authorize_teacher(account, publication.offer, publication.subject)
    publication.is_published = True
    publication.published_at = timezone.now()
    publication.save(update_fields=['public_snapshot', 'grading_snapshot', 'is_published', 'published_at', 'updated_at'])
    recipients = InstitutionalAccount.objects.filter(organization=account.organization, role='STUDENT', user__is_active=True,
        user__classroom_memberships__classroom_id=publication.offer.classroom_id,
        user__classroom_memberships__role='STUDENT', user__classroom_memberships__status='ACTIVE').select_related('user').distinct()
    for recipient in recipients:
        notify_user(recipient=recipient.user, title=f'{publication.get_kind_display()} publicada',
            message=f'{publication.subject} · {publication.title} · {publication.offer.name}',
            target_url=reverse('coursework:student-detail', args=[publication.pk]))
    return publication


@transaction.atomic
def enable_legacy_submission(publication):
    """Old public snapshots have no historical key. Accept answers for manual grading."""
    from decimal import Decimal, InvalidOperation
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    questions = publication.public_snapshot.get('questions', [])
    if publication.grading_snapshot or not questions:
        return publication
    keys = []
    for question in questions:
        try:
            points = Decimal(str(question['points']))
            if not points.is_finite() or points <= 0:
                return publication
        except (KeyError, InvalidOperation, ValueError):
            return publication
        keys.append({'type': 'multiple_choice' if question.get('options') else 'open_ended',
            'points': str(points), 'answer': '', 'manual': True})
    publication.grading_snapshot = keys
    publication.save(update_fields=['grading_snapshot'])
    return publication
