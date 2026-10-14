import base64
import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
import pypdfium2 as pdfium

from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.assessments.models import Assessment, AssessmentTechnique, QuestionImage
from features.assessments.services import add_bank_item_to_assessment
from features.paper_exams.documents import exam_pdf
from features.paper_exams.services import issue_run
from features.users_manager.models import Organization, ClassroomGroup, Classroom, ClassroomMembership


def image_upload(name='imagem.png', color='blue'):
    stream = BytesIO()
    Image.new('RGB', (160, 80), color).save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


class QuestionImageTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(username='author')
        self.other = get_user_model().objects.create_user(username='other')
        self.assessment = Assessment.objects.create(owner=self.user, subject='Geografia', topic='Mapas',
            technique=AssessmentTechnique.objects.first())
        self.client.force_login(self.user)

    def data(self, **overrides):
        data = {'question_type': 'multiple_choice', 'support_text': 'Texto de apoio original',
                'statement': 'Qual região está indicada?', 'options': 'Norte\nSul',
                'correct_answer': 'Norte', 'points': '1', 'default_points': '1',
                'subject': 'Geografia', 'topic': 'Mapas', 'image_description': 'Mapa do Brasil'}
        return {**data, **overrides}

    def create_bank(self):
        form = QuestionBankItemForm(self.data(), {'new_images': [image_upload(), image_upload('segunda.png', 'red')]})
        self.assertTrue(form.is_valid(), form.errors)
        return form.save_for(self.user)

    def test_upload_in_assessment_copies_text_and_ordered_images_to_bank(self):
        payload = self.data(new_images=[image_upload(), image_upload('segunda.png', 'red')])
        response = self.client.post(reverse('assessments:question-create', args=[self.assessment.pk]), payload)
        self.assertEqual(response.status_code, 302)
        question = self.assessment.questions.get()
        self.assertEqual(question.support_text, 'Texto de apoio original')
        self.assertEqual(list(question.images.values_list('pk', flat=True)),
                         list(question.bank_item.images.values_list('pk', flat=True)))
        self.assertEqual(question.images.count(), 2)
        page = self.client.get(reverse('assessments:index')).content.decode()
        self.assertLess(page.index('Texto de apoio original'), page.index('class="question-images"'))
        self.assertLess(page.index('class="question-images"'), page.index('Qual região está indicada?'))
        self.assertIn('enctype="multipart/form-data"', page)

    def test_derivation_keeps_images_and_edits_do_not_change_assessment_copy(self):
        item = self.create_bank()
        question = add_bank_item_to_assessment(self.assessment, item)
        derived = QuestionBankItemForm(self.data(statement='Novo comando'), source=item)
        self.assertTrue(derived.is_valid(), derived.errors)
        copy = derived.save_for(self.user, source=item)
        self.assertEqual(list(copy.images.all()), list(item.images.all()))
        response = self.client.post(reverse('assessments:bank-question-update', args=[item.pk]),
            self.data(support_text='Texto editado', remove_images=[i.pk for i in item.images.all()]))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        question.refresh_from_db()
        self.assertEqual(item.images.count(), 0)
        self.assertEqual(question.images.count(), 2)
        self.assertEqual(question.support_text, 'Texto de apoio original')

    def test_invalid_uploads_and_missing_description_do_not_save(self):
        cases = [SimpleUploadedFile('fake.png', b'not an image', content_type='image/png'),
                 SimpleUploadedFile('large.png', b'x' * (2 * 1024 * 1024 + 1))]
        for upload in cases:
            form = QuestionForm(self.data(), {'new_images': [upload]})
            self.assertFalse(form.is_valid())
            self.assertIn('new_images', form.errors)
        form = QuestionForm(self.data(image_description=''), {'new_images': [image_upload()]})
        self.assertFalse(form.is_valid())
        self.assertIn('image_description', form.errors)
        self.assertEqual(QuestionImage.objects.count(), 0)

    def test_five_image_limit_and_preservation_on_validation_error(self):
        form = QuestionForm(self.data(), {'new_images': [image_upload() for _ in range(6)]})
        self.assertFalse(form.is_valid())
        item = self.create_bank()
        form = QuestionBankItemForm(self.data(), {'new_images': [image_upload() for _ in range(4)]}, instance=item)
        self.assertFalse(form.is_valid())
        self.assertEqual(item.images.count(), 2)

    def test_private_image_route_and_cross_owner_mutations(self):
        item = self.create_bank()
        image = item.images.first()
        url = reverse('assessments:question-image', args=[image.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        response.close()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse('assessments:bank-question-update', args=[item.pk]),
            self.data(new_images=image_upload())).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_images_and_text_are_frozen_and_embedded_in_printed_exam(self):
        item = self.create_bank()
        question = add_bank_item_to_assessment(self.assessment, item)
        organization = Organization.objects.create(name='Escola', owner=self.user)
        group = ClassroomGroup.objects.create(name='Grupo', organization=organization, created_by=self.user)
        classroom = Classroom.objects.create(name='Turma', organization=organization, group=group, owner=self.user)
        ClassroomMembership.objects.create(classroom=classroom, user=self.other,
            role='STUDENT', status='ACTIVE', invited_by=self.user)
        run = issue_run(self.assessment, classroom, self.user)
        self.assertEqual(len(run.questions[0]['images']), 2)
        raw = base64.b64decode(run.questions[0]['images'][0]['data'])
        self.assertTrue(raw.startswith(b'\x89PNG'))
        question.images.clear()
        for asset in item.images.all():
            Path(asset.file.path).unlink()
        question.support_text = 'Texto alterado'
        question.save()
        document = pdfium.PdfDocument(exam_pdf(run))
        text = document[1].get_textpage().get_text_range()
        self.assertIn('Texto de apoio original', text)
        self.assertNotIn('Texto alterado', text)
        self.assertLess(text.index('Texto de apoio original'), text.index('Mapa do Brasil'))
        self.assertLess(text.index('Mapa do Brasil'), text.index('Qual região'))
        objects = list(document[1].get_objects())
        self.assertEqual(sum(obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE for obj in objects), 3)
        document.close()


class PublishedQuestionImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from contexts.institutions.coursework.tests import CourseworkTests
        CourseworkTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        setting = override_settings(MEDIA_ROOT=self.media.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.image = QuestionImage.objects.create(owner=self.teacher.user,
            file=image_upload(), description='Figura de frações')
        self.question.support_text = 'Leia o texto antes de observar a figura.'
        self.question.save()
        self.question.images.add(self.image)

    def test_student_can_only_access_images_in_accessible_published_snapshot(self):
        from contexts.institutions.coursework.services import publish
        url = reverse('assessments:question-image', args=[self.image.pk])
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 404)
        publish(self.teacher, self.publication)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()
        page = self.client.get(reverse('coursework:student-detail', args=[self.publication.pk]))
        self.assertContains(page, 'Figura de frações')
        self.assertContains(page, 'Leia o texto antes de observar a figura.')
        self.assertNotContains(page, 'GABARITO PRIVADO')
        self.question.images.clear()
        self.question.support_text = 'Rascunho novo'
        self.question.save()
        page = self.client.get(reverse('coursework:student-detail', args=[self.publication.pk]))
        self.assertContains(page, 'Figura de frações')
        self.assertNotContains(page, 'Rascunho novo')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.classroom.memberships.filter(user=self.student.user).delete()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_withdrawal_and_unrelated_roles_cannot_access_images(self):
        from contexts.institutions.coursework.services import publish
        publish(self.teacher, self.publication)
        url = reverse('assessments:question-image', args=[self.image.pk])
        for role in ('GUARDIAN', 'MANAGER', 'OPERATOR', 'ADMIN'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url).status_code, 404)
        self.publication.is_published = False
        self.publication.save()
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 404)
