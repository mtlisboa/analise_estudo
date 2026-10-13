import tempfile
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from features.accounts.institutional import provision_member
from features.accounts.tests import test_institutional_contexts as fixtures
from features.assessments.models import Assessment, AssessmentTechnique
from features.notifications.models import Notification
from features.paper_exams.models import AnswerSheet, ExamRun, ImportBatch, SheetResult
from features.users_manager.models import Classroom, ClassroomMembership
from ..planning.models import Period, Offer
from .models import FamilyRequest, GuardianLink, RequestMessage, SchoolEvent


class FamilyPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.InstitutionalContextTests.setUpTestData.__func__(cls)
        cls.other.owner.must_change_password = False
        cls.other.owner.onboarding_completed_at = timezone.now()
        cls.other.owner.save()
        cls.guardian = cls.users['GUARDIAN'].institutional_account
        cls.child = cls.users['STUDENT'].institutional_account
        cls.second = provision_member(cls.organization, cls.admin, registration='second', role='STUDENT',
            password='Initial-secret!92837', first_name='Segundo filho')
        cls.private = provision_member(cls.organization, cls.admin, registration='private', role='STUDENT',
            password='Initial-secret!92837', first_name='Aluno sem vínculo')
        for student in (cls.child, cls.second):
            GuardianLink.objects.create(guardian=cls.guardian, student=student, relationship='Pai', created_by=cls.admin)
        cls.second_class = Classroom.objects.create(name='Turma do segundo filho', organization=cls.organization,
            group=cls.classroom.group, owner=cls.admin)
        ClassroomMembership.objects.create(user=cls.second.user, classroom=cls.second_class, role='STUDENT', status='ACTIVE', invited_by=cls.admin)
        cls.period = Period.objects.create(organization=cls.organization, name='2026', starts_on=date(2026,1,1),
            ends_on=date(2026,12,31), published_at=timezone.now())
        cls.offer = Offer.objects.create(period=cls.period, classroom=cls.classroom, name='Turma publicada', grade='1',
            shift='MORNING', capacity=30, published_schedule=[{'subject':'MATEMÁTICA', 'teacher':'Professor publicado',
            'teacher_id':1, 'day':1, 'weekday':'Segunda', 'start':'08:00', 'end':'09:00', 'period_start':'2026-01-01',
            'period_end':'2026-12-31', 'classroom':'Turma publicada', 'period':'2026', 'code':'published-offer'}])
        technique = AssessmentTechnique.objects.create(code='family-test', name='Técnica')
        assessment = Assessment.objects.create(owner=cls.admin, subject='Matemática', topic='Teste', technique=technique)
        cls.exam_run = ExamRun.objects.create(assessment=assessment, classroom=cls.classroom, created_by=cls.admin,
            title='Prova de matemática', classroom_name=cls.classroom.name, questions=[])
        cls.batch = ImportBatch.objects.create(run=cls.exam_run, created_by=cls.admin, filename='test.csv')
        for child, score in [(cls.child, 8), (cls.second, 4), (cls.private, 9)]:
            sheet = AnswerSheet.objects.create(run=cls.exam_run, student=child.user,
                student_name=child.user.first_name, student_registration=child.registration)
            SheetResult.objects.create(sheet=sheet, batch=cls.batch, source_name='test', status='graded', score=score, maximum_score=10)
        for title, classroom, published in [('Evento geral', None, True), ('Evento filho', cls.classroom, True),
                ('Evento alheio', cls.other_classroom, True), ('Evento rascunho', None, False)]:
            SchoolEvent.objects.create(organization=cls.organization, classroom=classroom, title=title,
                description='Descrição', starts_at=timezone.now()+timedelta(days=1), ends_at=timezone.now()+timedelta(days=2),
                is_published=published, created_by=cls.admin)

    def setUp(self):
        self.client.force_login(self.guardian.user)

    def module(self, name, **query):
        return self.client.get(reverse('family:module', args=[name]), query)

    def test_multiple_children_and_own_results_only(self):
        self.assertContains(self.client.get(reverse('family:index')), 'Segundo filho')
        response = self.module('desempenho')
        self.assertContains(response, '60.0%')
        self.assertEqual(response.context['result_page'].paginator.count, 2)
        self.assertNotContains(response, 'Aluno sem vínculo')
        response = self.module('desempenho', child=self.child.pk)
        self.assertEqual(response.context['result_page'].paginator.count, 1)
        self.assertContains(response, '80.0%')
        self.assertEqual(self.module('desempenho', child=self.private.pk).status_code, 404)
        self.assertEqual(self.module('grade', child='invalid').status_code, 404)

    def test_grade_and_events_are_published_and_scoped(self):
        self.assertContains(self.module('grade'), 'MATEMÁTICA')
        response = self.module('eventos')
        self.assertContains(response, 'Evento geral')
        self.assertContains(response, 'Evento filho')
        self.assertNotContains(response, 'Evento alheio')
        self.assertNotContains(response, 'Evento rascunho')
        self.assertNotContains(self.module('eventos', child=self.second.pk), 'Evento filho')
        self.period.published_at = None
        self.period.save()
        self.assertNotContains(self.module('grade'), 'MATEMÁTICA')

    def test_general_contact_works_without_children_but_documents_need_child(self):
        GuardianLink.objects.filter(guardian=self.guardian).update(is_active=False)
        self.assertContains(self.client.get(reverse('family:index')), 'Nenhum filho vinculado')
        self.assertNotContains(self.module('eventos'), 'Evento geral')
        response = self.client.post(reverse('family:module', args=['contato']), {'title':'Contato geral', 'description':'Preciso de ajuda'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(FamilyRequest.objects.count(), 1)
        response = self.client.post(reverse('family:module', args=['documentos']), {'title':'Histórico', 'description':'Transferência'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FamilyRequest.objects.count(), 1)

    def test_document_request_cannot_spoof_student_guardian_or_organization(self):
        url = reverse('family:module', args=['documentos'])
        payload = {'title':'Histórico', 'description':'Transferência', 'student':self.private.pk,
            'guardian':self.admin.pk, 'organization':self.other.pk, 'status':'RESOLVED'}
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertFalse(FamilyRequest.objects.exists())
        payload['student'] = self.child.pk
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        ticket = FamilyRequest.objects.get()
        self.assertEqual(ticket.organization, self.organization)
        self.assertEqual(ticket.guardian, self.guardian)
        self.assertEqual(ticket.status, 'OPEN')
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title='Nova solicitação de responsável').exists())

    def ticket(self):
        return FamilyRequest.objects.create(organization=self.organization, guardian=self.guardian, student=self.child,
            kind='DOCUMENT', title='Declaração', description='Solicitação')

    def test_staff_response_document_download_and_revoked_link(self):
        ticket = self.ticket()
        url = reverse('family:request', args=[ticket.pk])
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.client.force_login(self.admin)
            response = self.client.post(url, {'text':'Documento disponível', 'status':'RESOLVED',
                'attachment': SimpleUploadedFile('declaracao.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf')})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Notification.objects.filter(recipient=self.guardian.user, title='Resposta da instituição').exists())
            ticket.refresh_from_db()
            self.assertEqual(ticket.status, 'RESOLVED')
            message = ticket.messages.get()
            download = reverse('family:attachment', args=[message.pk])
            self.client.force_login(self.guardian.user)
            response = self.client.get(download)
            self.assertEqual(response.status_code, 200)
            response.close()
            GuardianLink.objects.filter(guardian=self.guardian, student=self.child).update(is_active=False)
            self.assertEqual(self.client.get(download).status_code, 404)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_guardian_message_does_not_change_status_or_upload_document(self):
        ticket = self.ticket()
        response = self.client.post(reverse('family:request', args=[ticket.pk]), {'text':'Complemento', 'status':'RESOLVED'})
        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'OPEN')
        self.assertEqual(ticket.messages.count(), 1)

    def test_other_roles_and_institutions_cannot_read_family_data(self):
        ticket = self.ticket()
        self.client.force_login(self.users['TEACHER'])
        self.assertEqual(self.client.get(reverse('family:index')).status_code, 403)
        self.assertEqual(self.client.get(reverse('family:desk')).status_code, 403)
        self.client.force_login(self.other.owner)
        self.assertEqual(self.client.get(reverse('family:request', args=[ticket.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('family:desk')), 'Declaração')
        self.client.force_login(self.guardian.user)
        self.assertEqual(self.client.post(reverse('family:link-create'), {}).status_code, 403)

    def test_staff_can_create_and_revoke_links_but_cannot_link_across_institutions(self):
        self.client.force_login(self.users['OPERATOR'])
        response = self.client.post(reverse('family:link-create'), {'guardian':self.guardian.pk, 'student':self.private.pk,
            'relationship':'Responsável legal', 'is_active':'on'})
        self.assertEqual(response.status_code, 302)
        link = GuardianLink.objects.get(guardian=self.guardian, student=self.private)
        self.assertEqual(self.client.post(reverse('family:link-edit', args=[link.pk]), {
            'guardian':self.guardian.pk, 'student':self.private.pk, 'relationship':'Responsável legal'}).status_code, 302)
        link.refresh_from_db()
        self.assertFalse(link.is_active)
        invalid = GuardianLink(guardian=self.guardian, student=self.other.owner.institutional_account,
            relationship='Pai', created_by=self.admin)
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_event_publication_notifies_only_relevant_guardians(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('family:event-create'), {'title':'Reunião de pais', 'description':'Pauta',
            'starts_at':'2026-12-01T14:00', 'ends_at':'2026-12-01T15:00', 'location':'Sala 1',
            'classroom':self.classroom.pk, 'is_published':'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(recipient=self.guardian.user, title='Evento da instituição').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.private.user).exists())
        count = SchoolEvent.objects.count()
        response = self.client.post(reverse('family:event-create'), {'title':'Inválido', 'description':'Teste',
            'starts_at':'2026-12-01T14:00', 'ends_at':'2026-12-01T15:00', 'classroom':self.other.classrooms.first().pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SchoolEvent.objects.count(), count)

    def test_notifications_are_personal_and_mark_read_requires_post(self):
        own = Notification.objects.create(recipient=self.guardian.user, title='Aviso próprio')
        other = Notification.objects.create(recipient=self.admin, title='Aviso privado do admin')
        response = self.module('notificacoes')
        self.assertContains(response, 'Aviso próprio')
        self.assertNotContains(response, 'Aviso privado do admin')
        self.assertEqual(self.client.post(reverse('family:notification-read', args=[other.pk])).status_code, 404)
        url = reverse('family:notification-read', args=[own.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        own.refresh_from_db()
        self.assertIsNotNone(own.read_at)

    def test_corrected_result_notifies_once_and_respects_link_revocation(self):
        result = SheetResult.objects.get(sheet__student=self.child.user)
        with self.captureOnCommitCallbacks(execute=True):
            result.score = Decimal('7')
            result.save()
        self.assertEqual(Notification.objects.filter(recipient=self.guardian.user, title='Novo resultado acadêmico').count(), 1)
        with self.captureOnCommitCallbacks(execute=True):
            result.save()
        self.assertEqual(Notification.objects.filter(recipient=self.guardian.user, title='Novo resultado acadêmico').count(), 1)
        GuardianLink.objects.filter(guardian=self.guardian, student=self.child).update(is_active=False)
        with self.captureOnCommitCallbacks(execute=True):
            result.score = Decimal('6')
            result.save()
        self.assertEqual(Notification.objects.filter(recipient=self.guardian.user, title='Novo resultado acadêmico').count(), 1)

    def test_pdf_upload_rejects_other_file_types(self):
        ticket = self.ticket()
        self.client.force_login(self.admin)
        response = self.client.post(reverse('family:request', args=[ticket.pk]), {'text':'Teste', 'status':'RESOLVED',
            'attachment':SimpleUploadedFile('fake.pdf', b'not a pdf')})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ticket.messages.exists())

    def test_another_guardian_in_same_institution_cannot_read_request(self):
        ticket = self.ticket()
        other = provision_member(self.organization, self.admin, registration='other-parent', role='GUARDIAN',
            password='Initial-secret!92837', first_name='Outro responsável')
        other.user.must_change_password = False
        other.user.onboarding_completed_at = timezone.now()
        other.user.save()
        self.client.force_login(other.user)
        self.assertEqual(self.client.get(reverse('family:request', args=[ticket.pk])).status_code, 404)
        self.assertNotContains(self.module('documentos'), 'Declaração')
        self.assertNotContains(self.module('desempenho'), 'Prova de matemática')

    def test_performance_date_and_subject_filters(self):
        response = self.module('desempenho', subject='Português')
        self.assertEqual(response.context['result_page'].paginator.count, 0)
        response = self.module('desempenho', subject='matemática')
        self.assertEqual(response.context['result_page'].paginator.count, 2)
        response = self.module('desempenho', starts_on='2100-01-01')
        self.assertEqual(response.context['result_page'].paginator.count, 0)
        response = self.module('desempenho', starts_on='2026-12-31', ends_on='2026-01-01')
        self.assertContains(response, 'O início deve ser igual ou anterior ao fim.')
        self.assertEqual(response.context['result_page'].paginator.count, 0)
