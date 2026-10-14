from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import tests as fixtures
from .models import Publication, Submission
from .services import publish
from .submissions import revision
from features.assessments.models import Question, QuestionBankItem, Assessment
from features.notifications.models import Notification
from features.users_manager.models import Classroom, ClassroomMembership
from ..planning.models import Offer


class OnlineFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)
        cls.objective = Question.objects.create(assessment=cls.assessment, order=2,
            statement='Quanto é 2 + 2?', options=['3', '4'], correct_answer='4', points=3)

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def submit(self, **overrides):
        self.publication.refresh_from_db()
        data = {'revision': revision(self.publication), 'q1': 'Uma parte do todo.', 'q2': '1', **overrides}
        return self.client.post(reverse('coursework:student-detail', args=[self.publication.pk]), data)

    def test_teacher_bank_selection_apply_notification_student_submit_and_open_grading(self):
        response = self.client.post(reverse('assessments:bank-question-create'), {
            'subject': 'MATEMÁTICA', 'topic':'Somas', 'statement':'Quanto é 2 + 2?',
            'question_type':'multiple_choice', 'options':'3\n4', 'correct_answer':'4', 'default_points':'3'})
        self.assertEqual(response.status_code, 302)
        item = QuestionBankItem.objects.get(statement='Quanto é 2 + 2?')
        response = self.client.post(reverse('assessments:bank-questions-add-generic'), {'questions':[item.pk], 'title':'Prova do banco'})
        assessment = Assessment.objects.get(topic='Prova do banco')
        self.assertRedirects(response, reverse('coursework:apply', args=[assessment.pk]))
        url = reverse('coursework:apply', args=[assessment.pk])
        payload = {'offers':[self.offer.pk], 'kind':'EXAM', 'title':'Prova do banco'}
        self.assertRedirects(self.client.post(url, payload), reverse('coursework:index'))
        self.client.post(url, payload)
        obj = Publication.objects.get(assessment=assessment)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)
        self.assertEqual(Notification.objects.get(recipient=self.student.user).target_url,
                         reverse('coursework:student-detail', args=[obj.pk]))
        self.client.force_login(self.student.user)
        self.assertContains(self.client.get(reverse('institutions:student-discipline', args=[self.offer.code, 'MATEMÁTICA'])), 'Prova do banco')
        url = reverse('coursework:student-detail', args=[obj.pk])
        self.assertContains(self.client.get(url), 'Enviar respostas')
        self.assertContains(self.client.get(reverse('institutions:classroom', args=[self.classroom.pk])+'?subject=MATEM%C3%81TICA'), url)
        self.assertEqual(self.client.post(url, {'revision':revision(obj), 'q1':'1'}).status_code, 302)
        self.assertEqual(Submission.objects.get(publication=obj).score, Decimal('3'))

    def test_mixed_submission_is_idempotent_and_private_then_teacher_grades(self):
        publish(self.teacher, self.publication)
        self.client.force_login(self.student.user)
        response = self.client.get(reverse('coursework:student-detail', args=[self.publication.pk]))
        self.assertNotContains(response, 'GABARITO PRIVADO')
        self.assertEqual(self.submit().status_code, 302)
        self.submit(q1='Substituição indevida', q2='0')
        submission = Submission.objects.get()
        self.assertEqual(submission.answers['q1'], 'Uma parte do todo.')
        self.assertEqual(submission.automatic_score, 3)
        self.assertIsNone(submission.score)
        url = reverse('coursework:submission-review', args=[self.publication.pk, submission.pk])
        self.assertEqual(self.client.post(url, {'q1':'2'}).status_code, 403)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(url, {'q1':'9'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'q1':'1.5','feedback':'Boa justificativa.'}).status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.score, Decimal('4.5'))
        self.assertEqual(submission.reviews.count(), 1)
        self.question.correct_answer = 'Outro gabarito'
        self.question.save()
        with self.assertRaises(ValidationError):
            publish(self.teacher, self.publication)

    def test_invalid_choices_stale_revision_expired_and_revoked_membership(self):
        publish(self.teacher, self.publication)
        self.client.force_login(self.student.user)
        self.assertContains(self.submit(q2='999'), 'Faça uma escolha válida')
        self.assertContains(self.submit(revision='old'), 'Recarregue')
        self.assertFalse(Submission.objects.exists())
        self.publication.due_at = timezone.now()-timedelta(hours=1)
        self.publication.save()
        publish(self.teacher, self.publication)
        self.assertContains(self.submit(), 'prazo de envio')
        ClassroomMembership.objects.filter(user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.submit().status_code, 404)
        self.assertFalse(Submission.objects.exists())

    def test_multiple_classrooms_are_authorized_and_atomic(self):
        room = Classroom.objects.create(name='Turma B', organization=self.organization, owner=self.admin, group=self.classroom.group)
        ClassroomMembership.objects.create(classroom=room, user=self.teacher.user, role='TEACHER', status='ACTIVE', invited_by=self.admin)
        offer = Offer.objects.create(period=self.period, classroom=room, name='B', grade='1', shift='MORNING', capacity=30,
            published_schedule=self.offer.published_schedule)
        url = reverse('coursework:apply', args=[self.assessment.pk])
        data = {'offers':[self.offer.pk, offer.pk], 'kind':'EXAM', 'title':'Duas salas'}
        self.assertEqual(self.client.post(url,data).status_code, 302)
        self.assertEqual(Publication.objects.filter(assessment=self.assessment, is_published=True).count(), 2)
        ClassroomMembership.objects.filter(classroom=room, user=self.teacher.user).delete()
        data['title']='Não publicar'
        self.assertEqual(self.client.post(url,data).status_code, 200)
        self.assertFalse(Publication.objects.filter(title='Não publicar').exists())
