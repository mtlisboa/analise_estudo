from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from features.paper_exams.models import SheetResult
from features.notifications.services import notify_user
from .models import GuardianLink


@receiver(pre_save, sender=SheetResult)
def remember_result(sender, instance, **kwargs):
    instance._family_previous = sender.objects.filter(pk=instance.pk).values_list('status', 'score', 'maximum_score').first() if instance.pk else None


@receiver(post_save, sender=SheetResult)
def notify_result(sender, instance, raw=False, **kwargs):
    if raw or instance.status != 'graded' or instance.score is None:
        return
    if getattr(instance, '_family_previous', None) == (instance.status, instance.score, instance.maximum_score):
        return
    result_id = instance.pk

    def deliver():
        result = SheetResult.objects.select_related('sheet__run__classroom').filter(pk=result_id, status='graded').first()
        if result is None:
            return
        links = GuardianLink.objects.filter(student__user_id=result.sheet.student_id,
            student__organization_id=result.sheet.run.classroom.organization_id,
            student__role='STUDENT', student__user__is_active=True, guardian__role='GUARDIAN',
            guardian__organization__is_active=True, guardian__user__is_active=True, is_active=True).select_related('guardian__user')
        for link in links:
            notify_user(recipient=link.guardian.user, title='Novo resultado acadêmico',
                message='Uma prova foi corrigida ou revisada. Consulte o módulo de desempenho dos seus filhos.')
    transaction.on_commit(deliver)
