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
        return {'request_token': str(uuid.uuid4()), 'is_visible': 'on', 'offers': [self.offer.pk], 'kind': 'EXAM',
            'title': 'Aplicação independente', 'delivery_mode': 'online',
            'scheduled_at': '',
            'due_at': (timezone.now()+timedelta(days=1)).isoformat(), **changes}

    def schedule(self, **changes):
        data = self.payload(**{'scheduled_at': (timezone.now()+timedelta(hours=1)).isoformat(), **changes})
        response = self.client.post(reverse('coursework:apply', args=[self.assessment.pk]), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        return Publication.objects.get(request_token=data['request_token'])

    def make_due(self, publication):
        Publication.objects.filter(pk=publication.pk).update(scheduled_at=timezone.now()-timedelta(seconds=1))

    def test_three_actions_and_authoring_has_no_application_controls(self):
        page = self.client.get(reverse('assessments:index'))
        for text in ('Editar', 'Aplicar avaliação'):
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
        url = reverse('coursework:apply', args=[self.assessment.pk])
        for changes in ({'scheduled_at': (timezone.now()-timedelta(hours=1)).isoformat()},
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

    def test_application_starts_with_kind_and_prefills_instructions(self):
        self.assessment.instructions = 'Instruções originais da montagem'
        self.assessment.save()
        page = self.client.get(reverse('coursework:apply', args=[self.assessment.pk]))
        self.assertEqual(page.context['form']['instructions'].value(), self.assessment.instructions)
        body = page.content.decode()
        self.assertLess(body.index('name="kind"'), body.index('name="offers"'))
        self.assertContains(page, 'Física')
        self.assertContains(page, 'Virtual')
        self.assertContains(page, 'Aberta até')
        self.assertContains(page, 'data-virtual-settings')

    def test_hidden_virtual_application_can_be_released_once_with_saved_instructions(self):
        self.assessment.instructions = 'Instrução original'
        self.assessment.description = 'Descrição da montagem'
        self.assessment.content_topic = 'Frações equivalentes'
        self.assessment.save()
        data = self.payload(is_visible='', instructions='Instrução editada nesta aplicação', kind='ACTIVITY')
        url = reverse('coursework:apply', args=[self.assessment.pk])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        obj = Publication.objects.get(request_token=data['request_token'])
        self.assertFalse(obj.is_published)
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(obj.kind, 'ACTIVITY')
        self.assertEqual(obj.public_snapshot['instructions'], data['instructions'])
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.instructions, 'Instrução original')
        self.client.force_login(self.student.user)
        student_url = reverse('coursework:student-detail', args=[obj.pk])
        self.assertEqual(self.client.get(student_url).status_code, 404)
        release_url = reverse('coursework:application-make-visible', args=[obj.pk])
        self.assertEqual(self.client.post(release_url).status_code, 403)
        self.client.force_login(self.teacher.user)
        self.question.statement = 'Texto da questão alterado após a configuração'
        self.question.save()
        self.client.post(release_url)
        self.client.post(release_url)
        obj.refresh_from_db()
        self.assertTrue(obj.is_published)
        self.assertNotEqual(obj.public_snapshot['questions'][0]['statement'], self.question.statement)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)
        self.client.force_login(self.student.user)
        page = self.client.get(student_url)
        for text in ('Instrução editada nesta aplicação', 'Descrição da montagem', 'Frações equivalentes'):
            self.assertContains(page, text)

    def test_hidden_virtual_application_cannot_be_released_after_deadline(self):
        data = self.payload(is_visible='')
        self.client.post(reverse('coursework:apply', args=[self.assessment.pk]), data)
        obj = Publication.objects.get(request_token=data['request_token'])
        Publication.objects.filter(pk=obj.pk).update(due_at=timezone.now()-timedelta(seconds=1))
        self.client.post(reverse('coursework:application-make-visible', args=[obj.pk]))
        obj.refresh_from_db()
        self.assertFalse(obj.is_published)
        self.assertFalse(obj.release_visible)
        self.assertEqual(obj.application_status, 'completed')
        self.assertFalse(Notification.objects.exists())

    def test_physical_does_not_require_virtual_deadline_and_prints_application_instructions(self):
        from io import BytesIO
        from pypdf import PdfReader
        from features.paper_exams.documents import exam_pdf
        obj = self.schedule(delivery_mode='printed', due_at='', is_visible='', instructions='Use caneta azul.')
        self.assertIsNone(obj.due_at)
        self.assertTrue(obj.release_visible)
        self.assertEqual(obj.exam_run.context['instructions'], 'Use caneta azul.')
        pages = PdfReader(BytesIO(exam_pdf(obj.exam_run))).pages
        self.assertIn('Use caneta azul.', '\n'.join(page.extract_text() for page in pages))

    def test_schedule_respects_hidden_virtual_configuration(self):
        obj = self.schedule(is_visible='')
        self.make_due(obj)
        self.assertEqual(run_due_applications(), 1)
        obj.refresh_from_db()
        self.assertEqual(obj.application_status, 'completed')
        self.assertFalse(obj.is_published)
        self.assertFalse(Notification.objects.exists())
        started_at = obj.scheduled_at
        self.client.post(reverse('coursework:application-make-visible', args=[obj.pk]))
        obj.refresh_from_db()
        self.assertTrue(obj.is_published)
        self.assertEqual(obj.scheduled_at, started_at)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)


    def test_offer_picker_on_immediate_and_scheduled_application(self):
        for route in ('coursework:apply',):
            page = self.client.get(reverse(route, args=[self.assessment.pk]))
            self.assertContains(page, 'id="application-offer-dialog"', count=1)
            self.assertContains(page, 'Pesquisar minhas turmas')
            self.assertContains(page, 'Selecionar todas')
            self.assertContains(page, 'data-offer-choice')
            self.assertContains(page, self.offer.name)
            self.assertContains(page, 'name="offers"')
            form = page.context['form']
            self.assertIn(self.offer, form.fields['offers'].queryset)
            self.assertIn(self.offer.period.name, form.fields['offers'].label_from_instance(self.offer))

    def test_offer_selection_is_preserved_after_validation_error(self):
        data = self.payload(title='')
        response = self.client.post(reverse('coursework:apply', args=[self.assessment.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['offers'].value(), [str(self.offer.pk)])
        self.assertContains(response, 'checked')

    def test_physical_exam_creates_versioned_booklets_with_requested_shuffling(self):
        from features.assessments.models import Question
        for order in (3, 4):
            Question.objects.create(assessment=self.assessment, order=order, statement=f'Questão extra {order}',
                options=['A', 'B', 'C'], correct_answer='A', points=1)
        response = self.client.post(reverse('coursework:apply', args=[self.assessment.pk]),
            self.payload(delivery_mode='printed', due_at='', shuffle_questions='on', shuffle_options='on'))
        self.assertEqual(response.status_code, 302)
        publication = Publication.objects.get(title='Aplicação independente')
        self.assertEqual(set(publication.exam_run.variants), set('ABC'))
        self.assertTrue(publication.exam_run.context['shuffle_questions'])
        self.assertTrue(publication.exam_run.context['shuffle_options'])
        self.client.get(reverse('paper-exams:detail', args=[publication.exam_run_id]))
        keys = self.client.get(reverse('paper-exams:download', args=[publication.exam_run_id, 'gabaritos']))
        self.assertEqual(keys.status_code, 200)
        self.assertTrue(keys.content.startswith(b'%PDF'))

    def test_virtual_application_does_not_create_printed_versions(self):
        response = self.client.post(reverse('coursework:apply', args=[self.assessment.pk]),
            self.payload(shuffle_questions='on', shuffle_options='on'))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Publication.objects.get(title='Aplicação independente').exam_run_id)

    def test_unified_start_time_field_and_removed_schedule_action(self):
        for url in (reverse('assessments:index'), reverse('assessments:questionnaire-edit', args=[self.assessment.pk])):
            page = self.client.get(url)
            self.assertNotContains(page, 'Agendar aplicação')
            self.assertNotContains(page, reverse('coursework:schedule', args=[self.assessment.pk]))
        page = self.client.get(reverse('coursework:apply', args=[self.assessment.pk]))
        self.assertContains(page, 'Data e hora de início da aplicação')
        self.assertContains(page, 'name="scheduled_at"')
        self.assertFalse(page.context['form'].fields['scheduled_at'].required)

    def test_future_start_on_apply_route_is_not_released_early(self):
        data = self.payload(scheduled_at=(timezone.now()+timedelta(hours=2)).isoformat())
        response = self.client.post(reverse('coursework:apply', args=[self.assessment.pk]), data)
        self.assertEqual(response.status_code, 302)
        obj = Publication.objects.get(request_token=data['request_token'])
        self.assertEqual(obj.application_status, 'scheduled')
        self.assertFalse(obj.is_published)
        self.assertFalse(Notification.objects.exists())
        self.make_due(obj)
        self.assertEqual(run_due_applications(), 1)
        obj.refresh_from_db()
        self.assertTrue(obj.is_published)

    def test_legacy_schedule_link_redirects_to_application(self):
        self.assertRedirects(self.client.get(reverse('coursework:schedule', args=[self.assessment.pk])),
            reverse('coursework:apply', args=[self.assessment.pk]))

    def test_questionnaire_instructions_are_textarea_content_and_edits_survive_errors(self):
        from html import unescape
        import re
        original = 'Leia com atenção.\nJustifique suas respostas abertas.'
        self.assessment.instructions = original
        self.assessment.save(update_fields=['instructions'])
        url = reverse('coursework:apply', args=[self.assessment.pk])
        response = self.client.get(url)
        textarea = re.search(r'<textarea[^>]*name="instructions"[^>]*>(.*?)</textarea>', response.content.decode(), re.S)
        self.assertIsNotNone(textarea)
        self.assertEqual(unescape(textarea.group(1)).strip(), original)
        edited = 'Instruções editadas apenas para esta turma.'
        response = self.client.post(url, self.payload(title='', instructions=edited))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['instructions'].value(), edited)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.instructions, original)

    def test_format_is_hidden_and_keeps_initial_modal_choice(self):
        import re
        url = reverse('coursework:apply', args=[self.assessment.pk])
        for mode in ('online', 'printed'):
            response = self.client.get(url, {'delivery_mode': mode})
            self.assertNotContains(response, 'Formato de aplicação')
            self.assertNotContains(response, '<select name="delivery_mode"')
            hidden = re.search(r'<input[^>]*name="delivery_mode"[^>]*>', response.content.decode())
            self.assertIsNotNone(hidden)
            self.assertIn('type="hidden"', hidden.group())
            self.assertIn(f'value="{mode}"', hidden.group())
