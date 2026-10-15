import json

from django.test import TestCase
from django.urls import reverse
from django.template.loader import render_to_string
import pypdfium2 as pdfium

from . import test_question_images as fixtures

image_upload = fixtures.image_upload
from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.assessments.models import QuestionImage
from features.assessments.services import add_bank_item_to_assessment
from features.paper_exams.services import issue_run
from features.paper_exams.documents import exam_pdf
from features.users_manager.models import Organization, ClassroomGroup, Classroom, ClassroomMembership


class OrderedContentTests(TestCase):
    setUp = fixtures.QuestionImageTests.setUp
    data = fixtures.QuestionImageTests.data

    def create_item(self):
        payload = self.data(content_blocks=json.dumps([
            {'type': 'text', 'text': 'Primeiro paragrafo'},
            {'type': 'image', 'upload': 'block_image_first', 'description': 'Figura intermediaria'},
            {'type': 'text', 'text': 'Ultimo paragrafo'}]))
        form = QuestionBankItemForm(payload, {'block_image_first': image_upload()})
        self.assertTrue(form.is_valid(), form.errors)
        return form.save_for(self.user)

    def test_interleaved_upload_reorder_and_copy_preserve_sequence(self):
        item = self.create_item()
        self.assertEqual([b['type'] for b in item.content_blocks], ['text', 'image', 'text'])
        self.assertEqual(item.images.count(), 1)
        html = render_to_string('components/question_content.html', {'question': item})
        self.assertLess(html.index('Primeiro paragrafo'), html.index('Figura intermediaria'))
        self.assertLess(html.index('Figura intermediaria'), html.index('Ultimo paragrafo'))
        self.assertLess(html.index('Ultimo paragrafo'), html.index('Qual região'))
        question = add_bank_item_to_assessment(self.assessment, item)
        reordered = [item.content_blocks[2], item.content_blocks[1], item.content_blocks[0]]
        form = QuestionBankItemForm(self.data(content_blocks=json.dumps(reordered)), instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        edited = form.save_for(self.user)
        self.assertEqual(edited.content_blocks, reordered)
        question.refresh_from_db()
        self.assertEqual(question.content_blocks[0]['text'], 'Primeiro paragrafo')
        self.assertEqual(item.images.count(), 1)
        derived = QuestionBankItemForm(self.data(), source=edited)
        self.assertTrue(derived.is_valid(), derived.errors)
        self.assertEqual(derived.save_for(self.user, source=edited).content_blocks, reordered)

    def test_question_form_saves_blocks_to_both_question_and_bank(self):
        form = QuestionForm(self.data(content_blocks=json.dumps([
            {'type': 'text', 'text': 'Texto A'}, {'type': 'image', 'upload': 'block_image_a', 'description': 'Imagem A'},
            {'type': 'text', 'text': 'Texto B'}])), {'block_image_a': image_upload()})
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save(self.assessment)
        self.assertEqual(question.content_blocks, question.bank_item.content_blocks)
        self.assertEqual(question.support_text, 'Texto A\n\nTexto B')
        self.assertEqual(len(question.content_blocks), 3)

    def test_rejects_foreign_image_bad_list_missing_files_and_blank_paragraph(self):
        other = QuestionImage.objects.create(owner=self.other, file=image_upload(), description='Privada')
        for blocks in ([{'type': 'image', 'id': other.pk}], {'type': 'text'},
                [{'type': 'text', 'text': ''}], [{'type': 'image', 'upload': 'block_image_missing', 'description': 'Ausente'}],
                [{'type': 'script', 'text': 'invalid'}]):
            form = QuestionBankItemForm(self.data(content_blocks=json.dumps(blocks)))
            self.assertFalse(form.is_valid())
            self.assertIn('content_blocks', form.errors)
        self.assertEqual(QuestionImage.objects.count(), 1)

    def test_removal_clears_blocks_but_preserves_other_question_versions(self):
        item = self.create_item()
        question = add_bank_item_to_assessment(self.assessment, item)
        form = QuestionBankItemForm(self.data(content_blocks='[]'), instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.user)
        self.assertEqual(item.content_blocks, [])
        self.assertEqual(item.support_text, '')
        self.assertFalse(item.images.exists())
        self.assertEqual(question.images.count(), 1)

    def test_printed_snapshot_has_interleaved_immutable_content(self):
        item = self.create_item()
        add_bank_item_to_assessment(self.assessment, item)
        organization = Organization.objects.create(name='Escola', owner=self.user)
        group = ClassroomGroup.objects.create(name='Grupo', organization=organization, created_by=self.user)
        room = Classroom.objects.create(name='Turma', organization=organization, group=group, owner=self.user)
        ClassroomMembership.objects.create(classroom=room, user=self.other, role='STUDENT', status='ACTIVE', invited_by=self.user)
        run = issue_run(self.assessment, room, self.user)
        blocks = run.questions[0]['content_blocks']
        self.assertEqual([b['type'] for b in blocks], ['text', 'image', 'text'])
        self.assertTrue(blocks[1]['data'])
        with pdfium.PdfDocument(exam_pdf(run)) as document:
            text = '\n'.join(page.get_textpage().get_text_range() for page in document)
        self.assertLess(text.index('Primeiro paragrafo'), text.index('Figura intermediaria'))
        self.assertLess(text.index('Figura intermediaria'), text.index('Ultimo paragrafo'))
        self.assertLess(text.index('Ultimo paragrafo'), text.index('Qual região'))

    def test_widget_renders_in_question_form(self):
        html = str(QuestionBankItemForm()['content_blocks'])
        self.assertIn('data-content-block-editor', html)
        self.assertIn('Adicionar parágrafo', html)
        self.assertIn('Adicionar imagem', html)
        self.assertIn('data-image-pattern', html)
        self.assertContains(self.client.get(reverse('assessments:bank-question-create')), 'data-content-block-editor')
