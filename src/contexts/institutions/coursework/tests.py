from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.tests import test_institutional_contexts as fixtures
from features.assessments.models import Assessment, AssessmentTechnique, AssessmentType, Question
from features.notifications.models import Notification
from features.users_manager.models import ClassroomMembership
from ..planning.models import Period, Offer
from .models import Publication
from .services import publish


class CourseworkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.InstitutionalContextTests.setUpTestData.__func__(cls)
        cls.teacher = cls.users['TEACHER'].institutional_account
        cls.student = cls.users['STUDENT'].institutional_account
        cls.period = Period.objects.create(organization=cls.organization, name='2026', starts_on=date(2026,1,1),
            ends_on=date(2026,12,31), published_at=timezone.now())
        cls.offer = Offer.objects.create(period=cls.period, classroom=cls.classroom, name='Turma publicada', grade='1',
            shift='MORNING', capacity=30, published_schedule=[{'subject':'MATEMÁTICA', 'teacher':'Professor publicado',
            'teacher_id':cls.teacher.pk, 'day':1, 'weekday':'Segunda', 'start':'08:00', 'end':'09:00',
            'period_start':'2026-01-01','period_end':'2026-12-31','classroom':'Turma publicada','period':'2026','code':'code'}])
        cls.technique = AssessmentTechnique.objects.create(code='coursework-test', name='Técnica')
        cls.kind = AssessmentType.objects.create(code='coursework-test', name='Compreensão', default_technique=cls.technique)
        cls.assessment = Assessment.objects.create(owner=cls.teacher.user, subject='MATEMÁTICA', topic='Frações', technique=cls.technique)
        cls.question = Question.objects.create(assessment=cls.assessment, statement='Explique frações.',
            question_type='open_ended', correct_answer='GABARITO PRIVADO', explanation='EXPLICAÇÃO PRIVADA', points=2)
        cls.publication = Publication.objects.create(offer=cls.offer, subject='MATEMÁTICA', teacher=cls.teacher,
            assessment=cls.assessment, kind='EXAM', title='Prova de frações')

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def test_create_new_assessment_is_bound_to_teacher_and_published_discipline(self):
        response = self.client.post(reverse('coursework:create', args=[self.offer.code, 'MATEMÁTICA']),
            {'mode':'new', 'kind':'ACTIVITY', 'title':'Atividade nova', 'instructions':'Leia o capítulo 1',
            'subject':'DISCIPLINA INJETADA', 'topic':'Leitura', 'assessment_types':[self.kind.pk],
            'assembly_method':'manual', 'owner':self.admin.pk, 'is_published':'on'})
        self.assertEqual(response.status_code, 302)
        obj = Publication.objects.get(title='Atividade nova')
        self.assertEqual(obj.subject, 'MATEMÁTICA')
        self.assertEqual(obj.assessment.subject, 'MATEMÁTICA')
        self.assertEqual(obj.assessment.owner, self.teacher.user)
        self.assertFalse(obj.is_published)
        self.assertContains(self.client.get(reverse('coursework:edit', args=[obj.pk])), 'Leia o capítulo 1')

    def test_existing_assessment_must_belong_to_teacher_and_match_subject(self):
        foreign = Assessment.objects.create(owner=self.admin, subject='MATEMÁTICA', topic='Privada', technique=self.technique)
        url = reverse('coursework:create', args=[self.offer.code, 'MATEMÁTICA'])
        payload = {'mode':'existing', 'kind':'EXAM','title':'Outra prova','assessment':foreign.pk}
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertFalse(Publication.objects.filter(title='Outra prova').exists())
        payload['assessment'] = self.assessment.pk
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(Publication.objects.get(title='Outra prova').assessment, self.assessment)

    def test_teacher_cannot_create_for_unassigned_subject_or_inactive_membership(self):
        self.assertEqual(self.client.get(reverse('coursework:create', args=[self.offer.code, 'PORTUGUÊS'])).status_code, 403)
        ClassroomMembership.objects.filter(user=self.teacher.user).update(status='REMOVED')
        self.assertEqual(self.client.get(reverse('coursework:edit', args=[self.publication.pk])).status_code, 403)
        response = self.client.get(reverse('coursework:index'))
        self.assertNotContains(response, 'Prova de frações')

    def test_student_receives_publication_in_correct_discipline_without_answer_key(self):
        url = reverse('coursework:student-detail', args=[self.publication.pk])
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.teacher.user)
        response = self.client.post(reverse('coursework:action', args=[self.publication.pk,'publish']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user, title='Prova publicada').count(), 1)
        self.client.force_login(self.student.user)
        response = self.client.get(reverse('institutions:student-discipline', args=[self.offer.code,'MATEMÁTICA']))
        self.assertContains(response, 'Prova de frações')
        self.assertContains(response, url)
        response = self.client.get(url)
        self.assertContains(response, 'Explique frações.')
        self.assertNotContains(response, 'GABARITO PRIVADO')
        self.assertNotContains(response, 'EXPLICAÇÃO PRIVADA')
        self.publication.refresh_from_db()
        self.assertNotIn('correct_answer', self.publication.public_snapshot['questions'][0])

    def test_draft_changes_are_hidden_until_republication_and_notifications_are_idempotent(self):
        publish(self.teacher, self.publication)
        publish(self.teacher, self.publication)
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 1)
        self.question.statement = 'Texto do novo rascunho'
        self.question.save()
        self.client.post(reverse('coursework:edit', args=[self.publication.pk]),
            {'kind':'EXAM', 'title':'Novo título', 'instructions':'Instruções do rascunho'})
        self.client.force_login(self.student.user)
        url = reverse('coursework:student-detail', args=[self.publication.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Prova de frações')
        self.assertNotContains(response, 'Texto do novo rascunho')
        self.assertNotContains(response, 'Novo título')
        publish(self.teacher, self.publication)
        self.assertContains(self.client.get(url), 'Texto do novo rascunho')
        self.assertEqual(Notification.objects.filter(recipient=self.student.user).count(), 2)

    def test_student_membership_and_publication_withdrawal_revoke_access(self):
        publish(self.teacher, self.publication)
        self.client.force_login(self.student.user)
        url = reverse('coursework:student-detail', args=[self.publication.pk])
        ClassroomMembership.objects.filter(user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.client.get(url).status_code, 404)
        ClassroomMembership.objects.filter(user=self.student.user).update(status='ACTIVE')
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(reverse('coursework:action', args=[self.publication.pk,'withdraw'])).status_code, 302)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_prova_needs_questions_but_activity_can_use_instructions(self):
        self.assessment.questions.all().delete()
        self.client.post(reverse('coursework:action', args=[self.publication.pk,'publish']))
        self.publication.refresh_from_db()
        self.assertFalse(self.publication.is_published)
        self.publication.kind = 'ACTIVITY'
        self.publication.instructions = 'Faça um resumo do capítulo.'
        self.publication.save()
        publish(self.teacher, self.publication)
        self.client.force_login(self.student.user)
        self.assertContains(self.client.get(reverse('coursework:student-detail', args=[self.publication.pk])), 'Faça um resumo')

    def test_question_actions_are_owned_and_post_only(self):
        url = reverse('coursework:question-create', args=[self.publication.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'question_type':'open_ended','statement':'Explique o conceito.',
            'correct_answer':'Resposta esperada', 'points':'1.00'}).status_code, 302)
        self.assertEqual(self.assessment.questions.count(), 2)
        question = self.assessment.questions.last()
        self.assertEqual(self.client.post(reverse('coursework:question-remove', args=[self.publication.pk,question.pk])).status_code, 302)
        self.assertEqual(self.assessment.questions.count(), 1)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('coursework:index')).status_code, 403)

    def test_no_cross_institution_or_other_teacher_publication_access(self):
        self.other.owner.must_change_password = False
        self.other.owner.save()
        self.client.force_login(self.other.owner)
        self.assertEqual(self.client.get(reverse('coursework:edit', args=[self.publication.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('coursework:student-detail', args=[self.publication.pk])).status_code, 403)

    def test_derived_discipline_requires_published_schedule_for_student_and_teacher(self):
        publish(self.teacher, self.publication)
        self.period.published_at = None
        self.period.save()
        self.assertEqual(self.client.get(reverse('coursework:edit', args=[self.publication.pk])).status_code, 403)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(reverse('coursework:student-detail', args=[self.publication.pk])).status_code, 404)

    def test_published_content_keeps_interleaved_order_until_republished(self):
        from features.assessments.models import QuestionImage
        from features.assessments.tests.test_question_images import image_upload
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            image = QuestionImage.objects.create(owner=self.teacher.user, file=image_upload(), description='Figura intercalada')
            self.question.images.add(image)
            blocks = [{'type': 'text', 'text': 'Paragrafo antes'},
                {'type': 'image', 'id': image.pk, 'description': image.description},
                {'type': 'text', 'text': 'Paragrafo depois'}]
            self.question.content_blocks = blocks
            self.question.save()
            publish(self.teacher, self.publication)
            self.client.force_login(self.student.user)
            url = reverse('coursework:student-detail', args=[self.publication.pk])
            page = self.client.get(url, {'iniciar': '1'}).content.decode()
            self.assertLess(page.index('Paragrafo antes'), page.index('Figura intercalada'))
            self.assertLess(page.index('Figura intercalada'), page.index('Paragrafo depois'))
            self.assertLess(page.index('Paragrafo depois'), page.index('Explique frações.'))
            self.question.content_blocks = list(reversed(blocks))
            self.question.save()
            self.publication.refresh_from_db()
            self.assertEqual(self.publication.public_snapshot['questions'][0]['content_blocks'], blocks)
