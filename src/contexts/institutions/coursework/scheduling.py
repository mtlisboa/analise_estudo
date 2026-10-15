"""Durable jobs: all state and notification writes share the release transaction."""
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from features.notifications.services import notify_user
from .models import Publication
from .services import activate_publication, authorize_teacher

logger = logging.getLogger(__name__)


@transaction.atomic
def execute_application(pk):
    publication = Publication.objects.select_for_update().select_related('teacher__user', 'offer__period').get(pk=pk)
    if publication.application_status != 'scheduled' or publication.scheduled_at > timezone.now():
        return False
    authorize_teacher(publication.teacher, publication.offer, publication.subject)
    if not publication.teacher.user.is_active or not publication.teacher.organization.is_active:
        raise ValidationError('Professor ou instituição inativos.')
    if publication.delivery_mode == 'printed':
        if not publication.exam_run_id:
            raise ValidationError('A aplicação física não possui uma emissão preparada.')
        activate_publication(publication.teacher, publication)
        notify_user(recipient=publication.teacher.user, title='Aplicação física de avaliação',
            message=f'{publication.subject} · {publication.title} · {publication.offer.name}. A prova está pronta para impressão.',
            target_url=reverse('paper-exams:detail', args=[publication.exam_run_id]))
    else:
        if publication.due_at and publication.due_at <= timezone.now():
            raise ValidationError('O prazo terminou antes da aplicação. Configure uma nova aplicação.')
        activate_publication(publication.teacher, publication)
    publication.application_status = 'completed'
    publication.application_error = ''
    publication.save(update_fields=['application_status', 'application_error'])
    return True


def run_due_applications():
    count = 0
    ids = Publication.objects.filter(application_status='scheduled', scheduled_at__lte=timezone.now()).order_by('scheduled_at').values_list('pk', flat=True)
    for pk in list(ids[:100]):
        try:
            count += bool(execute_application(pk))
        except Exception:
            logger.exception('Failed to execute assessment application %s', pk)
            # Keep failures visible to the teacher. Never publish after losing authorization.
            with transaction.atomic():
                publication = Publication.objects.select_for_update().get(pk=pk)
                if publication.application_status == 'scheduled':
                    publication.application_status = 'failed'
                    publication.application_error = 'Não foi possível aplicar. Confira os vínculos da turma e o prazo; cancele e configure novamente.'
                    publication.save(update_fields=['application_status', 'application_error'])
                    notify_user(recipient=publication.teacher.user, title='Falha na aplicação agendada',
                        message=publication.application_error,
                        target_url=reverse('coursework:apply', args=[publication.assessment_id]))
    return count
