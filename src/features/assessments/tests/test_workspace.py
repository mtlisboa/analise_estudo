import re
import uuid
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

    def apply_assessment(self, assessment, mode='online'):
        data = {'request_token': str(uuid.uuid4()), 'offers': [self.offer.pk], 'kind': assessment.kind,
            'title': assessment.topic, 'delivery_mode': mode,
            'due_at': (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')}
        response = self.client.post(reverse('coursework:apply', args=[assessment.pk]), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')

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
        self.apply_assessment(assessment)
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
        self.assertFalse(Publication.objects.filter(assessment__topic='Questionário compacto').exists())
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(topic='Inválido',questions=[])).status_code,200)
        self.assertFalse(Assessment.objects.filter(topic='Inválido').exists())
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(topic='Sem prazo',due_at='')).status_code,302)
        self.assertTrue(Assessment.objects.filter(topic='Sem prazo').exists())

    def test_printed_questionnaire_finalization_requests_missing_answer_sheets(self):
        self.assertEqual(self.client.post(reverse('assessments:questionnaire-create'),self.payload(delivery_mode='printed')).status_code,302)
        assessment=Assessment.objects.get(topic='Questionário compacto')
        self.apply_assessment(assessment, 'printed')
        run=ExamRun.objects.get(assessment=assessment)
        self.assertEqual(run.sheets.count(),1)
        self.assertContains(self.client.get(reverse('coursework:apply',args=[assessment.pk])), 'Finalizar aplicação física')
        self.assertRedirects(self.client.post(reverse('coursework:application-finalize',args=[Publication.objects.get(assessment=assessment).pk])),reverse('assessments:corrections'))
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
        self.apply_assessment(assessment, 'printed')
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

    def test_question_scores_are_defined_per_assessment_and_not_in_bank(self):
        from decimal import Decimal
        payload = self.payload(**{f'points_{self.private.pk}': '2.50', f'points_{self.public.pk}': '7.00', 'shuffle_options': 'on'})
        response = self.client.post(reverse('assessments:questionnaire-create'), payload)
        self.assertEqual(response.status_code, 302)
        assessment = Assessment.objects.get(topic='Questionário compacto')
        self.assertTrue(assessment.shuffle_options)
        self.assertEqual(assessment.questions.get(bank_item=self.private).points, Decimal('2.50'))
        self.assertEqual(assessment.questions.get(bank_item=self.public).points, Decimal('7.00'))
        self.private.refresh_from_db()
        self.assertEqual(self.private.default_points, 1)
        page = self.client.get(response.url)
        self.assertContains(page, f'name="points_{self.private.pk}"')
        self.apply_assessment(assessment)
        publication = Publication.objects.get(assessment=assessment)
        self.assertEqual({q['points'] for q in publication.public_snapshot['questions']}, {'2.50', '7.00'})
        self.client.force_login(self.student.user)
        answers = {f'q{i+1}': str(question['options'].index('Dois'))
            for i, question in enumerate(publication.public_snapshot['questions'])}
        answers['revision'] = revision(publication)
        self.assertEqual(self.client.post(reverse('coursework:student-detail', args=[publication.pk]), answers).status_code, 302)
        self.assertEqual(Submission.objects.get(publication=publication).score, Decimal('9.50'))
        self.client.force_login(self.teacher.user)
        old_options = assessment.questions.get(bank_item=self.private).options
        self.private.options = ['Questão alterada', 'Outra resposta']
        self.private.correct_answer = 'Outra resposta'
        self.private.save()
        edited = self.client.post(response.url, payload)
        self.assertEqual(edited.status_code, 302, edited.context['form'].errors if edited.context else '')
        self.assertEqual(assessment.questions.get(bank_item=self.private).options, old_options)

    def test_invalid_score_is_not_saved(self):
        payload = self.payload(**{f'points_{self.private.pk}': '0', f'points_{self.public.pk}': '2'})
        response = self.client.post(reverse('assessments:questionnaire-create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'points_{self.private.pk}', response.context['form'].errors)
        self.assertFalse(Assessment.objects.filter(topic='Questionário compacto').exists())

    def test_scores_and_option_order_cannot_change_after_submission(self):
        payload = self.payload(**{f'points_{self.private.pk}': '2', f'points_{self.public.pk}': '3'})
        response = self.client.post(reverse('assessments:questionnaire-create'), payload)
        self.assertEqual(response.status_code, 302)
        assessment = Assessment.objects.get(topic='Questionário compacto')
        self.apply_assessment(assessment)
        publication = Publication.objects.get(assessment=assessment)
        Submission.objects.create(publication=publication, student=self.student.user, answers={}, maximum_score=5)
        payload[f'points_{self.private.pk}'] = '9'
        denied = self.client.post(response.url, payload)
        self.assertContains(denied, 'já foi aplicado')
        self.assertEqual(assessment.questions.get(bank_item=self.private).points, 2)
        payload[f'points_{self.private.pk}'] = '2'
        payload['shuffle_options'] = 'on'
        denied = self.client.post(response.url, payload)
        self.assertContains(denied, 'já foi aplicado')
        assessment.refresh_from_db()
        self.assertFalse(assessment.shuffle_options)

    def test_modal_question_order_is_saved_reopened_and_used_in_publication(self):
        ordered = [self.public.pk, self.private.pk]
        payload = self.payload(questions=ordered)
        response = self.client.post(reverse('assessments:questionnaire-create'), payload)
        self.assertEqual(response.status_code, 302)
        obj = Assessment.objects.get(topic='Questionário compacto')
        self.assertEqual(list(obj.questions.values_list('bank_item_id', flat=True)), ordered)
        page = self.client.get(response.url)
        self.assertEqual([item.pk for item in page.context['selected_questions']], ordered)
        self.assertContains(page, 'data-picker-selected')
        self.assertContains(page, 'Públicas e privadas')
        self.apply_assessment(obj)
        publication = Publication.objects.get(assessment=obj)
        self.assertEqual([q['statement'] for q in publication.public_snapshot['questions']],
            [self.public.statement, self.private.statement])
        payload['questions'] = list(reversed(ordered))
        self.assertEqual(self.client.post(response.url, payload).status_code, 302)
        self.assertEqual(list(obj.questions.values_list('bank_item_id', flat=True)), list(reversed(ordered)))
        self.assertEqual(list(obj.questions.values_list('order', flat=True)), [1, 2])

    def test_duplicate_selection_is_rejected_and_applied_order_is_immutable(self):
        duplicate = self.client.post(reverse('assessments:questionnaire-create'), self.payload(questions=[self.private.pk, self.private.pk]))
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, 'cada questão apenas uma vez')
        self.assertFalse(Assessment.objects.filter(topic='Questionário compacto').exists())
        payload = self.payload(questions=[self.public.pk, self.private.pk], delivery_mode='printed')
        response = self.client.post(reverse('assessments:questionnaire-create'), payload)
        self.assertEqual(response.status_code, 302)
        obj = Assessment.objects.get(topic='Questionário compacto')
        self.apply_assessment(obj, 'printed')
        run = ExamRun.objects.get(assessment=obj)
        self.assertEqual([q['statement'] for q in run.questions], [self.public.statement, self.private.statement])
        payload['questions'] = [self.private.pk, self.public.pk]
        denied = self.client.post(response.url, payload)
        self.assertContains(denied, 'já foi aplicado')
        self.assertEqual(list(obj.questions.values_list('bank_item_id', flat=True)), [self.public.pk, self.private.pk])
