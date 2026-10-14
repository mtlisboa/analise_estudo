from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from features.users_manager.models import Organization, InstitutionalAccount
from features.assessments.bank_access import available_questions
from features.assessments.catalog import import_math_catalog
from features.assessments.forms import AddBankQuestionsForm
from features.assessments.models import Assessment, AssessmentType, QuestionBankItem


class InstitutionalCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='catalog-owner')
        cls.organization = Organization.objects.create(name='Escola A', owner=cls.owner)
        cls.other = Organization.objects.create(name='Escola B', owner=cls.owner)
        cls.teacher = User.objects.create_user(username='catalog-teacher')
        cls.student = User.objects.create_user(username='catalog-student')
        cls.outsider = User.objects.create_user(username='catalog-outsider')
        for user, organization, role in [(cls.teacher, cls.organization, 'TEACHER'),
                                        (cls.student, cls.organization, 'STUDENT'),
                                        (cls.outsider, cls.other, 'TEACHER')]:
            InstitutionalAccount.objects.create(user=user, organization=organization,
                role=role, registration=user.username, email=f'{user.username}@school.test',
                created_by=cls.owner)
        cls.imported = import_math_catalog(cls.organization)
        cls.item = QuestionBankItem.objects.filter(organization=cls.organization).first()

    def test_catalog_is_valid_and_repeatable(self):
        self.assertEqual(self.imported, 638)
        self.assertEqual(import_math_catalog(self.organization), 0)
        self.assertEqual(QuestionBankItem.objects.count(), 638)
        for item in QuestionBankItem.objects.all():
            item.clean()
            self.assertIn(item.correct_answer, item.options)
            self.assertFalse(item.source_metadata['reviewed'])

    def test_scope_and_revocation(self):
        self.assertEqual(available_questions(self.teacher).count(), 638)
        self.assertFalse(available_questions(self.student).exists())
        self.assertFalse(available_questions(self.outsider).exists())
        InstitutionalAccount.objects.filter(user=self.teacher).update(role='STUDENT')
        self.assertFalse(available_questions(self.teacher).exists())

    def test_teacher_can_select_shared_question_but_outsider_cannot(self):
        assessment = Assessment.objects.create(owner=self.teacher, subject='Matemática',
            topic='Teste', technique=AssessmentType.objects.first().default_technique)
        form = AddBankQuestionsForm({'assessment': assessment.pk, 'questions': [self.item.pk]}, owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(AddBankQuestionsForm(owner=self.outsider).fields['questions'].queryset.filter(pk=self.item.pk).exists())
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('assessments:bank-questions-add-generic'),
            {'assessment': assessment.pk, 'questions': [self.item.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(assessment.questions.get().bank_item_id, self.item.pk)

    def test_listing_and_original_protection(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('assessments:question-bank'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['questions']), 30)
        self.assertContains(response, 'Não revisada')
        self.assertEqual(self.client.get(reverse('assessments:bank-question-update', args=[self.item.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('assessments:bank-question-derive', args=[self.item.pk])).status_code, 200)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('assessments:bank-question-derive', args=[self.item.pk])).status_code, 404)
