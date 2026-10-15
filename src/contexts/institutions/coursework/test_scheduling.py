import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import tests as fixtures
from .models import Publication
from .scheduling import run_due_applications
from .services import publish
from features.notifications.models import Notification
from features.users_manager.models import ClassroomMembership


class AssessmentApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def payload(self, **changes):
        return {'request_token': str(uuid.uuid4()), 'offers': [self.offer.pk], 'kind': 'EXAM',
            'title': 'Aplicação independente', 'delivery_mode': 'online',
            'scheduled_at': (timezone.now()+timedelta(hours=1)).isoformat(),
            'due_at': (timezone.now()+timedelta(days=1)).isoformat(), **changes}

    def schedule(self, **changes):
        data = self.payload(**changes)
        response = self.client.post(reverse('coursework:schedule', args=[self.assessment.pk]), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        return Publication.objects.get(request_token=data['request_token'])

    def make_due(self, publication):
        Publication.objects.filter(pk=publication.pk).update(scheduled_at=timezone.now()-timedelta(seconds=1))

    def test_three_actions_and_authoring_has_no_application_controls(self):
        page = self.client.get(reverse('assessments:index'))
        for text in ('Editar', 'Aplicar avaliação', 'Agendar aplicação'):
            self.assertContains(page, text)
        page = self.client.get(reverse('assessments:questionnaire-edit', args=[self.assessment.pk]))
        for name in ('offers', 'due_at', 'delivery_mode', 'is_visible'):
            self.assertNotContains(page, f'name="{name}"')

    def test_schedule_freezes_configuration_and_releases_once_without_user_request(self):
        obj = self.schedule()
        self.assertFalse(obj.is_published)
        self.assertEqual(run_due_applications(), 0)
        self.assertFalse(Notification.objects.exists())
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(reverse('coursework:student-detail', args=[obj.pk])).status_code, 404)
        old = self.question.statement
        self.question.statement = 'Nova versão para outra aplicação'
        self.question.points = 9
        self.question.save()
        self.make_due(obj)
        call_command('run_application_scheduler', '--once')
        self.assertEqual(run_due_applications(), 0)
        obj.refresh_from_db()
        self.assertTrue(obj.is_published)
        self.assertEqual(obj.application_status, 'completed')
        self.assertEqual(obj.public_snapshot['questions'][0]['statement'], old)
        self.assertEqual(obj.public_snapshot['questions'][0]['points'], '2.00')
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)
        page = self.client.get(reverse('coursework:student-detail', args=[obj.pk]))
        self.assertContains(page, old)
        self.assertNotContains(page, 'GABARITO PRIVADO')

    def test_physical_prepares_paper_and_notifies_teacher_and_students_only_when_due(self):
        obj = self.schedule(delivery_mode='printed', due_at='')
        self.assertIsNotNone(obj.exam_run_id)
        self.assertEqual(obj.exam_run.sheets.count(), 1)
        self.assertFalse(obj.is_published)
        self.assertFalse(Notification.objects.exists())
        self.make_due(obj)
        self.assertEqual(run_due_applications(), 1)
        self.assertEqual(run_due_applications(), 0)
        notice = Notification.objects.get(recipient=self.teacher.user)
        self.assertEqual(notice.target_url, reverse('paper-exams:detail', args=[obj.exam_run_id]))
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)
        obj.refresh_from_db()
        self.assertEqual(obj.public_snapshot['delivery_mode'], 'printed')
        self.client.force_login(self.student.user)
        page = self.client.get(reverse('coursework:student-detail', args=[obj.pk]))
        self.assertNotContains(page, 'Enviar respostas')
        self.assertEqual(self.client.post(reverse('coursework:student-detail', args=[obj.pk]), {}).status_code, 403)

    def test_cancelled_job_never_runs_and_other_teacher_or_student_cannot_cancel(self):
        obj = self.schedule()
        url = reverse('coursework:application-cancel', args=[obj.pk])
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.make_due(obj)
        self.assertEqual(run_due_applications(), 0)
        self.assertFalse(Notification.objects.exists())

    def test_revoked_teacher_fails_without_publishing_or_duplicate_failure_notice(self):
        obj = self.schedule()
        self.make_due(obj)
        ClassroomMembership.objects.filter(user=self.teacher.user).update(status='REMOVED')
        with self.assertLogs('contexts.institutions.coursework.scheduling', level='ERROR'):
            self.assertEqual(run_due_applications(), 0)
        obj.refresh_from_db()
        self.assertEqual(obj.application_status, 'failed')
        self.assertFalse(obj.is_published)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.teacher.user).count(), 1)
        run_due_applications()
        self.assertEqual(Notification.objects.filter(recipient=self.teacher.user).count(), 1)

    def test_invalid_times_and_delivery_and_no_questions_leave_no_jobs(self):
        url = reverse('coursework:schedule', args=[self.assessment.pk])
        for changes in ({'scheduled_at': ''}, {'scheduled_at': (timezone.now()-timedelta(hours=1)).isoformat()},
                        {'due_at': (timezone.now()-timedelta(hours=1)).isoformat()}, {'delivery_mode': 'other'}, {'due_at': ''}):
            self.assertEqual(self.client.post(url, self.payload(**changes)).status_code, 200)
        self.assessment.questions.all().delete()
        self.assertEqual(self.client.post(url, self.payload()).status_code, 200)
        self.assertEqual(Publication.objects.filter(application_status='scheduled').count(), 0)

    def test_independent_repeated_applications_and_double_click_protection(self):
        url = reverse('coursework:apply', args=[self.assessment.pk])
        data = self.payload()
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(Publication.objects.filter(request_token=data['request_token']).count(), 1)
        other = self.payload(delivery_mode='printed')
        self.assertEqual(self.client.post(url, other).status_code, 302)
        self.assertEqual(Publication.objects.filter(application_status='completed').count(), 2)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.delivery_mode, 'online')

    def test_legacy_publish_endpoint_cannot_release_a_schedule_early(self):
        obj = self.schedule()
        self.client.post(reverse('coursework:action', args=[obj.pk, 'publish']))
        obj.refresh_from_db()
        self.assertFalse(obj.is_published)
        self.assertFalse(Notification.objects.exists())

    def test_partial_activation_rolls_back_and_is_reported_as_failure(self):
        obj = self.schedule()
        self.make_due(obj)
        with patch('contexts.institutions.coursework.services.notify_user', side_effect=RuntimeError('unavailable')):
            with self.assertLogs('contexts.institutions.coursework.scheduling', level='ERROR'):
                run_due_applications()
        obj.refresh_from_db()
        self.assertFalse(obj.is_published)
        self.assertEqual(obj.application_status, 'failed')
        self.assertFalse(Notification.objects.filter(recipient=self.student.user).exists())

    def test_physical_finalization_is_per_application_and_excludes_future_schedules(self):
        pending = self.schedule(delivery_mode='printed', due_at='')
        url = reverse('coursework:apply', args=[self.assessment.pk])
        data = self.payload(delivery_mode='printed', due_at='')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        done = Publication.objects.get(request_token=data['request_token'])
        self.assertEqual(self.client.post(reverse('coursework:application-finalize', args=[done.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse('coursework:application-finalize', args=[pending.pk])).status_code, 404)
        waiting = self.client.get(reverse('assessments:corrections')).context['waiting']
        self.assertEqual([item['run'].pk for item in waiting], [done.exam_run_id])
        pending.refresh_from_db()
        self.assertIsNone(pending.finalized_at)
