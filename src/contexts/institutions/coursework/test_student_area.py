import io
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen import canvas

from . import tests as fixtures
from .models import PDFModule, Publication, Submission
from .services import publish
from .submissions import revision
from features.assessments.models import Assessment, Question, QuestionBankItem
from features.users_manager.models import OrganizationMembership, ClassroomMembership
from features.users_manager.permissions import can_manage_classroom
from features.notifications.models import Notification


class StudentAreaIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)
        cls.bank = QuestionBankItem.objects.create(owner=cls.teacher.user, title='Operações', subject='MATEMÁTICA',
            topic='Somas', statement='Quanto é 2 + 2?', options=['3','4'],correct_answer='4',default_points=3)
        cls.objective = Question.objects.create(assessment=cls.assessment, order=2, bank_item=cls.bank,
            statement=cls.bank.statement, options=cls.bank.options, correct_answer='4', points=3)

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def pdf_upload(self):
        stream = io.BytesIO()
        pdf = canvas.Canvas(stream)
        pdf.drawString(40, 780, 'Material da disciplina')
        pdf.showPage()
        pdf.drawString(40, 780, 'Segunda pagina do material')
        pdf.save()
        return SimpleUploadedFile('material.pdf', stream.getvalue(),content_type='application/pdf')

    def test_teacher_with_active_classroom_role_can_add_pdf_without_legacy_org_flag(self):
        OrganizationMembership.objects.filter(organization=self.organization,user=self.teacher.user).delete()
        self.assertTrue(can_manage_classroom(self.teacher.user,self.classroom))
        room=reverse('institutions:classroom',args=[self.classroom.pk])+'?subject=MATEM%C3%81TICA'
        response=self.client.get(room)
        self.assertContains(response,'Adicionar atividade ou prova')
        self.assertContains(response,'name="document"')
        self.assertEqual(self.client.post(reverse('coursework:pdf-create',args=[self.offer.code,'MATEMÁTICA']),
            {'title':'Leitura da semana','document':self.pdf_upload()}).status_code,302)
        module=PDFModule.objects.get()
        self.assertEqual(Notification.objects.get(recipient=self.student.user).target_url,reverse('coursework:pdf-reader',args=[module.pk]))
        self.client.force_login(self.student.user)
        self.assertContains(self.client.get(room),'Leitura da semana')
        discipline=self.client.get(reverse('institutions:student-discipline',args=[self.offer.code,'MATEMÁTICA']))
        self.assertContains(discipline,reverse('coursework:pdf-reader',args=[module.pk]))
        self.assertContains(self.client.get(reverse('coursework:pdf-reader',args=[module.pk])),'data-pdf-page')
        pdf=self.client.get(reverse('coursework:pdf-open',args=[module.pk]))
        self.assertEqual(pdf.status_code,200)
        self.assertTrue(b''.join(pdf.streaming_content).startswith(b'%PDF-'))
        ClassroomMembership.objects.filter(user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.client.get(reverse('coursework:pdf-reader',args=[module.pk])).status_code,403)

    def test_drafts_are_visible_to_the_teacher_but_hidden_from_student(self):
        room=reverse('institutions:classroom',args=[self.classroom.pk])+'?subject=MATEM%C3%81TICA'
        self.assertContains(self.client.get(room),self.publication.title)
        self.assertContains(self.client.get(room),'Rascunho')
        self.client.force_login(self.student.user)
        self.assertNotContains(self.client.get(room),self.publication.title)

    def test_classroom_creation_requires_separate_application_before_student_submission(self):
        url=reverse('assessments:questionnaire-create')+f'?offer={self.offer.pk}&subject=MATEM%C3%81TICA'
        response=self.client.get(url)
        self.assertNotContains(response, 'name="is_visible"')
        data={'topic':'Prova publicada da turma','subject':'MATEMÁTICA','kind':'EXAM','delivery_mode':'online',
            'due_at':(timezone.now()+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),'offers':[self.offer.pk],
            'questions':[self.bank.pk],'is_visible':'on'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertFalse(Publication.objects.filter(title=data['topic']).exists())
        assessment = Assessment.objects.get(topic=data['topic'])
        self.assertEqual(self.client.post(reverse('coursework:apply', args=[assessment.pk]), {
            'request_token': str(uuid.uuid4()), 'offers': [self.offer.pk], 'kind': 'EXAM',
            'title': data['topic'], 'delivery_mode': 'online', 'due_at': data['due_at']}).status_code, 302)
        obj=Publication.objects.get(title=data['topic'])
        self.assertEqual(obj.kind,'EXAM')
        self.client.force_login(self.student.user)
        url=reverse('coursework:student-detail',args=[obj.pk])
        self.assertContains(self.client.get(url),'Iniciar atividade')
        self.assertContains(self.client.get(url+'?iniciar=1'),'name="q1"')
        self.assertEqual(self.client.post(url+'?iniciar=1',{'revision':revision(obj),'q1':'1'}).status_code,302)
        submission=Submission.objects.get(publication=obj)
        self.assertEqual(submission.score,3)
        self.assertContains(self.client.get(url),'Entrega registrada')

    def test_old_publication_accepts_answers_without_guessing_historical_key(self):
        publish(self.teacher,self.publication)
        self.publication.refresh_from_db()
        old=dict(self.publication.public_snapshot)
        for q in old['questions']:q.pop('type',None)
        Publication.objects.filter(pk=self.publication.pk).update(grading_snapshot=[],public_snapshot=old)
        self.objective.correct_answer='3'
        self.objective.save()
        self.client.force_login(self.student.user)
        url=reverse('coursework:student-detail',args=[self.publication.pk])
        self.assertContains(self.client.get(url),'Iniciar atividade')
        self.publication.refresh_from_db()
        self.assertEqual(self.client.post(url+'?iniciar=1',{'revision':revision(self.publication),'q1':'Uma parte do todo','q2':'1'}).status_code,302)
        submission=Submission.objects.get()
        self.assertEqual(submission.automatic_score,0)
        self.assertIsNone(submission.score)
        self.assertTrue(all(q['manual'] for q in self.publication.grading_snapshot))
        self.client.force_login(self.teacher.user)
        review=reverse('coursework:submission-review',args=[self.publication.pk,submission.pk])
        self.assertEqual(self.client.post(review,{'q1':'2','q2':'3','feedback':'Conferido na prova publicada.'}).status_code,302)
        submission.refresh_from_db()
        self.assertEqual(submission.score,Decimal('5'))

    def test_pdf_pages_render_and_keep_access_controls(self):
        self.client.post(reverse('coursework:pdf-create',args=[self.offer.code,'MATEMÁTICA']),
            {'title':'PDF com duas páginas','document':self.pdf_upload()})
        module=PDFModule.objects.get()
        self.client.force_login(self.student.user)
        reader=reverse('coursework:pdf-reader',args=[module.pk])
        self.assertContains(self.client.get(reader),'Próxima página')
        self.assertContains(self.client.get(reader+'?page=2'),'Segunda pagina do material')
        page=reverse('coursework:pdf-page',args=[module.pk,2])
        response=self.client.get(page)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get(reverse('coursework:pdf-page',args=[module.pk,3])).status_code,404)
        ClassroomMembership.objects.filter(user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.client.get(page).status_code,403)
