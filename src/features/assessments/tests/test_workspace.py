import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from contexts.institutions.coursework import tests as fixtures
from contexts.institutions.coursework.models import Publication, Submission
from contexts.institutions.coursework.submissions import revision
from features.notifications.models import Notification
from features.paper_exams.models import ExamRun
from features.users_manager.models import ClassroomMembership
from features.assessments.models import Assessment, QuestionBankItem


class QuestionnaireWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)
        cls.private = QuestionBankItem.objects.create(owner=cls.teacher.user, title='Minha questão privada', subject='MATEMÁTICA',
            topic='Frações', statement='Texto completo da questão privada', options=['Um','Dois'],correct_answer='Dois')
        cls.public = QuestionBankItem.objects.create(owner=cls.teacher.user, organization=cls.organization, title='Questão da instituição',
            subject='MATEMÁTICA',topic='Frações',statement='Texto completo compartilhado',options=['Um','Dois'],correct_answer='Dois')

    def setUp(self):
        self.client.force_login(self.teacher.user)

    def payload(self, **overrides):
        return {'topic':'Questionário compacto','subject':'MATEMÁTICA','questions':[self.private.pk,self.public.pk],
            'offers':[self.offer.pk],'delivery_mode':'online','due_at':(timezone.now()+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            'is_visible':'on',**overrides}

    def test_two_sidebar_entries_and_bank_visibility_preview_permissions(self):
        response=self.client.get(reverse('assessments:index'))
        self.assertEqual([row['label'] for row in response.context['evaluation_links']],['Banco de questões','Questionários'])
        response=self.client.get(reverse('assessments:question-bank'))
        self.assertContains(response,self.public.title)
        self.assertNotContains(response,self.private.title)
        self.assertNotContains(response,self.public.statement)
        response=self.client.get(reverse('assessments:question-bank')+'?scope=private')
        self.assertContains(response,self.private.title)
        self.assertNotContains(response,self.public.title)
        url=reverse('assessments:question-preview',args=[self.private.pk])
        self.assertContains(self.client.get(url),self.private.statement)
        self.other.owner.must_change_password=False
        self.other.owner.save(update_fields=['must_change_password'])
        self.client.force_login(self.other.owner)
        self.assertEqual(self.client.get(url).status_code,404)
        response=self.client.get(reverse('assessments:question-bank')+'?scope=private&fragment=1')
        self.assertNotIn(self.private.title,response.json()['html'])

    def test_cursor_paging_has_no_duplicates_and_modal_uses_same_visibility_rules(self):
        for i in range(65):
            QuestionBankItem.objects.create(owner=self.teacher.user,title=f'Questão {i}',subject='MATEMÁTICA',topic='Frações',
                statement='Texto',options=['Um','Dois'],correct_answer='Dois')
        url=reverse('assessments:question-bank')+'?scope=private&fragment=1&select=1'
        first=self.client.get(url).json()
        first_ids=re.findall(r'data-question-id="(\d+)"',first['html'])
        second=self.client.get(url+f'&before={first["next"]}').json()
        second_ids=re.findall(r'data-question-id="(\d+)"',second['html'])
        self.assertEqual(len(first_ids),30)
        self.assertEqual(len(second_ids),30)
        self.assertFalse(set(first_ids)&set(second_ids))
        self.assertIn('data-select-question',first['html'])

    def test_online_questionnaire_publishes_in_classroom_and_student_submits(self):
        response=self.client.post(reverse('assessments:questionnaire-create'),self.payload())
        self.assertEqual(response.status_code,302)
        assessment=Assessment.objects.get(topic='Questionário compacto')
        publication=Publication.objects.get(assessment=assessment)
        self.assertTrue(publication.is_published)
        self.assertEqual(assessment.questions.count(),2)
        self.assertEqual(Notification.objects.get(recipient=self.student.user).target_url,reverse('coursework:student-detail',args=[publication.pk]))
        self.client.force_login(self.student.user)
        self.assertContains(self.client.get(reverse('institutions:classroom',args=[self.classroom.pk])+'?subject=MATEM%C3%81TICA'), 'Questionário compacto')
        url=reverse('coursework:student-detail',args=[publication.pk])
        self.assertEqual(self.client.post(url,{'revision':revision(publication),'q1':'1','q2':'1'}).status_code,302)
        self.assertEqual(Submission.objects.get().score,2)

    def test_hidden_questionnaire_and_validation(self):
        response=self.client.post(reverse('assessments:questionnaire-create'),self.payload(is_visible=''))
        self.assertEqual(response.status_code,302)
        self.assertFalse(Publication.objects.get(assessment__topic='Questionário compacto').is_published)
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(topic='Inválido',questions=[])).status_code,200)
        self.assertFalse(Assessment.objects.filter(topic='Inválido').exists())
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(topic='Sem prazo',due_at='')).status_code,200)
        self.assertFalse(Assessment.objects.filter(topic='Sem prazo').exists())

    def test_printed_questionnaire_finalization_requests_missing_answer_sheets(self):
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(delivery_mode='printed')).status_code,302)
        assessment=Assessment.objects.get(topic='Questionário compacto')
        run=ExamRun.objects.get(assessment=assessment)
        self.assertEqual(run.sheets.count(),1)
        self.assertContains(self.client.get(reverse('assessments:questionnaire-edit',args=[assessment.pk])), 'Finalizar aplicação física')
        self.assertRedirects(self.client.post(reverse('assessments:questionnaire-finalize',args=[assessment.pk])),reverse('assessments:corrections'))
        response=self.client.get(reverse('assessments:corrections'))
        self.assertEqual(len(response.context['waiting']),1)
        self.assertEqual(response.context['waiting'][0]['missing'],1)
        publication=Publication.objects.get(assessment=assessment)
        self.client.force_login(self.student.user)
        url=reverse('coursework:student-detail',args=[publication.pk])
        self.assertNotContains(self.client.get(url),'Enviar respostas')
        self.assertEqual(self.client.post(url,{}).status_code,403)
        self.assertFalse(Submission.objects.exists())

    def test_issued_questions_are_preserved_and_revoked_teachers_lose_corrections(self):
        self.client.post(reverse('assessments:questionnaire-create'),self.payload(delivery_mode='printed'))
        assessment=Assessment.objects.get(topic='Questionário compacto')
        response=self.client.post(reverse('assessments:questionnaire-edit',args=[assessment.pk]),self.payload(delivery_mode='printed',questions=[self.private.pk]))
        self.assertContains(response,'já foi aplicado')
        self.assertEqual(assessment.questions.count(),2)
        ClassroomMembership.objects.filter(user=self.teacher.user).update(status='REMOVED')
        self.assertEqual(len(self.client.get(reverse('assessments:corrections')).context['waiting']),0)

    def test_classroom_creation_uses_same_editor_and_context_initialization(self):
        response=self.client.get(reverse('institutions:classroom',args=[self.classroom.pk])+'?subject=MATEM%C3%81TICA')
        self.assertContains(response,reverse('assessments:questionnaire-create'))
        url=reverse('assessments:questionnaire-create')+f'?offer={self.offer.pk}&subject=MATEM%C3%81TICA'
        response=self.client.get(url)
        self.assertEqual(response.context['form'].initial['subject'],'MATEMÁTICA')
        self.assertContains(response,'question-picker-dialog')
