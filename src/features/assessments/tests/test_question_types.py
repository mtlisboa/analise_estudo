import json
from django.test import TestCase
from django.urls import reverse
from . import test_question_images as fixtures
from features.assessments.forms import QuestionBankItemForm
from features.assessments.services import add_bank_item_to_assessment


class QuestionTypeTests(TestCase):
    setUp = fixtures.QuestionImageTests.setUp
    data = fixtures.QuestionImageTests.data

    def test_closed_question_uses_unlabelled_correctness_markers_and_no_bank_score(self):
        rows = [{'text': 'Resposta incorreta', 'correct': False}, {'text': 'Resposta correta', 'correct': True}]
        form = QuestionBankItemForm(self.data(alternatives=json.dumps(rows), default_points='99'))
        self.assertNotIn('default_points', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.user)
        self.assertEqual(item.options, ['Resposta incorreta', 'Resposta correta'])
        self.assertEqual(item.correct_answer, 'Resposta correta')
        self.assertEqual(item.default_points, 1)
        page = self.client.get(reverse('assessments:question-preview', args=[item.pk]))
        self.assertContains(page, 'Correta')
        self.assertContains(page, 'Errada')
        self.assertNotContains(page, '<ol type="A">')
        self.assertNotContains(page, 'pontos')

    def test_closed_question_requires_unique_texts_and_one_correct(self):
        for rows in ([{'text': 'A', 'correct': False}, {'text': 'B', 'correct': False}],
                [{'text': 'A', 'correct': True}, {'text': 'B', 'correct': True}],
                [{'text': 'A', 'correct': True}, {'text': 'A', 'correct': False}]):
            form = QuestionBankItemForm(self.data(alternatives=json.dumps(rows)))
            self.assertFalse(form.is_valid())
            self.assertIn('alternatives', form.errors)

    def test_open_question_stores_lines_copies_them_and_discards_closed_answers(self):
        form = QuestionBankItemForm(self.data(question_type='open_ended', alternatives='[]', answer_lines='12'))
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.user)
        self.assertEqual(item.answer_lines, 12)
        self.assertEqual(item.options, [])
        self.assertEqual(item.correct_answer, '')
        self.assertEqual(add_bank_item_to_assessment(self.assessment, item).answer_lines, 12)
        for count in ('', '0', '41', '-1'):
            invalid = QuestionBankItemForm(self.data(question_type='open_ended', alternatives='[]', answer_lines=count))
            self.assertFalse(invalid.is_valid(), count)
            self.assertIn('answer_lines', invalid.errors)

    def test_open_line_count_is_frozen_in_printed_assessment(self):
        from features.users_manager.models import Organization, ClassroomGroup, Classroom, ClassroomMembership
        from features.paper_exams.services import issue_run
        from features.paper_exams.documents import exam_pdf
        import pypdfium2
        form = QuestionBankItemForm(self.data(question_type='open_ended', alternatives='[]', answer_lines='12'))
        self.assertTrue(form.is_valid(), form.errors)
        question = add_bank_item_to_assessment(self.assessment, form.save_for(self.user))
        organization = Organization.objects.create(name='Escola', owner=self.user)
        group = ClassroomGroup.objects.create(name='Grupo', organization=organization, created_by=self.user)
        room = Classroom.objects.create(name='Sala', owner=self.user, organization=organization, group=group)
        ClassroomMembership.objects.create(classroom=room, user=self.other, role='STUDENT', status='ACTIVE', invited_by=self.user)
        run = issue_run(self.assessment, room, self.user)
        self.assertEqual(run.questions[0]['answer_lines'], 12)
        question.answer_lines = 1
        question.save()
        self.assertEqual(run.questions[0]['answer_lines'], 12)
        with pypdfium2.PdfDocument(exam_pdf(run)) as pdf:
            self.assertGreaterEqual(len(pdf), 2)

    def test_question_form_renders_iterative_editor_without_legacy_textarea(self):
        form = QuestionBankItemForm()
        self.assertTrue(form['options'].is_hidden)
        self.assertTrue(form['correct_answer'].is_hidden)
        self.assertIn('data-alternative-list', str(form['alternatives']))
        response = self.client.get(reverse('assessments:bank-question-create'))
        self.assertContains(response, 'Adicionar alternativa')
        self.assertContains(response, 'Lista de alternativas')
        self.assertNotContains(response, '<textarea name="options"')
        self.assertNotContains(response, '<textarea name="correct_answer"')
