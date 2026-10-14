from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from features.users_manager.models import Organization, InstitutionalAccount
from features.assessments.models import QuestionBankItem, Assessment, AssessmentType
from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.assessments.bank_access import available_questions


class QuestionSharingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='owner')
        cls.school = Organization.objects.create(name='A', owner=cls.owner)
        cls.other_school = Organization.objects.create(name='B', owner=cls.owner)
        for name, org, role in [('teacher', cls.school, 'TEACHER'), ('peer', cls.school, 'TEACHER'),
                                ('manager', cls.school, 'MANAGER'), ('other', cls.other_school, 'TEACHER'),
                                ('other_manager', cls.other_school, 'MANAGER'), ('student', cls.school, 'STUDENT')]:
            user = User.objects.create_user(username=name)
            setattr(cls, name, user)
            InstitutionalAccount.objects.create(user=user, organization=org, role=role,
                registration=name, email=f'{name}@test.example', created_by=cls.owner)
        cls.personal = User.objects.create_user(username='personal')
        cls.item = QuestionBankItem.objects.create(owner=cls.teacher, organization=cls.school,
            subject='Matemática', topic='Soma', statement='1+1?', options=['1', '2'], correct_answer='2')

    def data(self, **kwargs):
        result = dict(subject='Matemática', topic='Soma', statement='1+1?', question_type='multiple_choice',
            options='1\n2', correct_answer='2', default_points='1', points='1')
        result.update(kwargs)
        return result

    def publish(self, scope='everyone', user=None, item=None):
        self.client.force_login(user or self.manager)
        return self.client.post(reverse('assessments:institutional-sharing'),
            {'question_id': (item or self.item).pk, 'external_visibility': scope})

    def test_opt_in_default_private_and_shared_creation(self):
        form = QuestionBankItemForm(self.data(), owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        private = form.save_for(self.teacher)
        self.assertIsNone(private.organization_id)
        self.assertFalse(available_questions(self.peer).filter(pk=private.pk).exists())
        form = QuestionBankItemForm(self.data(share_with_institution='on'), owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        shared = form.save_for(self.teacher)
        self.assertEqual(shared.organization, self.school)
        self.assertTrue(available_questions(self.peer).filter(pk=shared.pk).exists())
        self.assertFalse(available_questions(self.other).filter(pk=shared.pk).exists())

    def test_question_inside_assessment_can_be_shared(self):
        assessment = Assessment.objects.create(owner=self.teacher, subject='Matemática', topic='Soma',
            technique=AssessmentType.objects.first().default_technique)
        form = QuestionForm(self.data(share_with_institution='on'), owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(assessment).bank_item.organization, self.school)

    def test_teacher_cannot_choose_another_institution_or_publish(self):
        form = QuestionBankItemForm(self.data(share_with_institution='on', sharing_organization=self.other_school.pk), owner=self.teacher)
        self.assertFalse(form.is_valid())
        self.assertEqual(self.publish(user=self.teacher).status_code, 403)
        self.assertEqual(self.publish(user=self.other_manager).status_code, 404)
        self.item.refresh_from_db()
        self.assertEqual(self.item.external_visibility, 'institution')

    def test_manager_scopes_and_revocation(self):
        self.assertEqual(self.publish('institutions').status_code, 302)
        self.assertTrue(available_questions(self.other).filter(pk=self.item.pk).exists())
        self.assertFalse(available_questions(self.personal).filter(pk=self.item.pk).exists())
        self.assertFalse(available_questions(self.student).filter(pk=self.item.pk).exists())
        self.assertEqual(self.publish('everyone').status_code, 302)
        self.assertTrue(available_questions(self.personal).filter(pk=self.item.pk).exists())
        self.assertTrue(available_questions(self.student).filter(pk=self.item.pk).exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.sharing_approved_by, self.manager)
        self.assertEqual(self.publish('institution').status_code, 302)
        self.assertFalse(available_questions(self.other).filter(pk=self.item.pk).exists())

    def test_edit_requires_reapproval_and_withdrawal_removes_institution(self):
        self.publish()
        self.item.refresh_from_db()
        form = QuestionBankItemForm(self.data(statement='Quanto é 1+1?', share_with_institution='on'), instance=self.item, owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.teacher)
        self.assertEqual(item.external_visibility, 'institution')
        self.assertIsNone(item.sharing_approved_by)
        self.assertFalse(available_questions(self.personal).filter(pk=item.pk).exists())
        form = QuestionBankItemForm(self.data(), instance=item, owner=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.teacher)
        self.assertIsNone(item.organization_id)
        self.assertEqual(self.publish(item=item).status_code, 404)
        self.assertFalse(available_questions(self.peer).filter(pk=item.pk).exists())

    def test_manager_page_and_teacher_flag_render(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse('assessments:institutional-sharing')), 'Todos os usuários cadastrados')
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('assessments:bank-question-create')), 'share_with_institution')
        self.assertContains(self.client.get(reverse('assessments:bank-question-create')), 'share_with_institution')

    def test_images_follow_scope_and_existing_assessment_copies_survive(self):
        import tempfile
        from django.core.files.base import ContentFile
        from django.test import override_settings
        from features.assessments.models import QuestionImage
        from features.assessments.services import add_bank_item_to_assessment
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            image = QuestionImage.objects.create(owner=self.teacher, description='Figura',
                file=ContentFile(b'example', name='test.png'))
            self.item.images.add(image)
            url = reverse('assessments:question-image', args=[image.pk])
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.publish('institutions')
            self.client.force_login(self.other)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            assessment = Assessment.objects.create(owner=self.other, subject='Matemática', topic='Soma',
                technique=AssessmentType.objects.first().default_technique)
            add_bank_item_to_assessment(assessment, self.item)
            self.publish('institution')
            self.client.force_login(self.other)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.client.force_login(self.personal)
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_ai_generation_respects_teacher_opt_in(self):
        from unittest.mock import patch
        self.client.force_login(self.teacher)
        with patch('features.assessments.services.request_ai_json', return_value={
            'statement': '2+2?', 'question_type': 'multiple_choice',
            'options': ['3', '4'], 'correct_answer': '4', 'points': 1,
        }):
            response = self.client.post(reverse('assessments:bank-question-ai-create'), {
                'subject': 'Matemática', 'topic': 'Soma', 'instructions': 'Crie uma soma',
                'share_with_institution': 'on',
            })
        self.assertEqual(response.status_code, 302)
        item = QuestionBankItem.objects.get(statement='2+2?')
        self.assertEqual(item.organization, self.school)
        self.assertEqual(item.external_visibility, 'institution')
