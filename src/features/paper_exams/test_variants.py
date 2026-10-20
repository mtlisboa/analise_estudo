import csv
import io
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.urls import reverse
import cv2
from pypdf import PdfReader
from . import tests as fixtures
from .models import SheetResult
from .services import issue_run, process_upload, pages
from .documents import answer_sheets_pdf, exam_pdf, variant_keys_pdf
from features.assessments.models import Question
from features.users_manager.models import ClassroomMembership


class VariantTests(TestCase):
    def setUp(self):
        fixtures.PaperExamTests.setUp(self)
        for number in range(2):
            user = get_user_model().objects.create_user(username=f'variant-student-{number}')
            ClassroomMembership.objects.create(classroom=self.classroom, user=user, role='STUDENT', status='ACTIVE', invited_by=self.teacher)
        self.run = issue_run(self.assessment, self.classroom, self.teacher, versioned=True, shuffle_questions=True, shuffle_options=True)

    def test_three_stable_patterns_and_correct_keys(self):
        self.assertEqual(set(self.run.variants), set('ABC'))
        self.assertEqual(set(self.run.sheets.values_list('variant', flat=True)), set('ABC'))
        patterns = set()
        for version, questions in self.run.variants.items():
            patterns.add(tuple((q['id'], tuple(q['options'])) for q in questions))
            for q in questions:
                self.assertEqual(q['options']['ABCDE'.index(q['correct'])], 'Dois')
        self.assertEqual(len(patterns), 3)
        old = self.run.variants.copy()
        self.assessment.questions.update(statement='Editada', correct_answer='Um')
        self.run.refresh_from_db()
        self.assertEqual(self.run.variants, old)

    def test_csv_grades_each_version_with_its_key(self):
        data = io.StringIO()
        writer = csv.writer(data)
        writer.writerow(['sheet_id', 'student_id', 'q1', 'q2', 'q3'])
        for sheet in self.run.sheets.all():
            writer.writerow([sheet.pk, sheet.student_id] + [q['correct'] for q in sheet.questions])
        batch = process_upload(self.run, self.teacher, SimpleUploadedFile('answers.csv', data.getvalue().encode()))
        self.assertEqual(batch.errors, [])
        self.assertEqual(SheetResult.objects.filter(sheet__run=self.run, score=Decimal('7.50'), status='graded').count(), 3)

    def test_omr_resolves_variant_from_signed_sheet_identity(self):
        sheet = self.run.sheets.get(variant='C')
        image = next(iter(pages(answer_sheets_pdf(self.run, [sheet]), '.pdf')))[1]
        for index, question in enumerate(sheet.questions):
            fixtures.PaperExamTests.mark(self, image, index, 'ABCDE'.index(question['correct']))
        _, png = cv2.imencode('.png', image)
        batch = process_upload(self.run, self.teacher, SimpleUploadedFile('photo.png', png.tobytes()))
        self.assertEqual(batch.errors, [])
        result = SheetResult.objects.get(sheet=sheet)
        self.assertEqual(result.score, Decimal('7.50'))
        self.assertEqual(result.answers, [q['correct'] for q in sheet.questions])

    def test_open_questions_last_and_key_pdf(self):
        Question.objects.create(assessment=self.assessment, order=0, statement='Resposta aberta', question_type='open_ended', points=1)
        run = issue_run(self.assessment, self.classroom, self.teacher, versioned=True, shuffle_questions=True, shuffle_options=True)
        for questions in run.variants.values():
            self.assertEqual(questions[-1]['type'], 'open_ended')
            self.assertTrue(all(q['type'] == 'multiple_choice' for q in questions[:-1]))
        keys = PdfReader(io.BytesIO(variant_keys_pdf(run)))
        self.assertEqual(len(keys.pages), 3)
        for page, version in zip(keys.pages, 'ABC'):
            self.assertIn(f'Gabarito {version}', page.extract_text())
            self.assertIn('Correção manual', page.extract_text())
        document = PdfReader(io.BytesIO(exam_pdf(run)))
        text = '\n'.join(page.extract_text() for page in document.pages)
        for version in 'ABC':
            self.assertIn(f'Prova {version}', text)

    def test_key_revision_translates_to_each_version(self):
        from contexts.institutions.analysis.services import effective_questions
        from types import SimpleNamespace
        from unittest.mock import patch
        revision = SimpleNamespace(question_index=1, correct='A', annulled=False, created_at=0, pk=0)
        with patch.object(type(self.run), 'key_revisions', create=True) as manager:
            manager.all.return_value = [revision]
            for sheet in self.run.sheets.all():
                questions = effective_questions(self.run, sheet)
                target = next(q for q in questions if q['id'] == self.run.questions[0]['id'])
                self.assertEqual(target['options']['ABCDE'.index(target['correct'])], 'Um')

    def test_not_enough_permutations_is_explicit(self):
        from .variants import make_variants
        with self.assertRaisesMessage(ValidationError, 'combinações suficientes'):
            make_variants([{'id':1, 'type':'multiple_choice', 'options':['Sim','Não'], 'correct':'A'}], 'seed', False, True)

    def test_same_application_seed_keeps_patterns_across_classroom_runs(self):
        first = issue_run(self.assessment, self.classroom, self.teacher, versioned=True,
            shuffle_questions=True, shuffle_options=True, variant_seed='same-application')
        second = issue_run(self.assessment, self.classroom, self.teacher, versioned=True,
            shuffle_questions=True, shuffle_options=True, variant_seed='same-application')
        self.assertEqual(first.variants, second.variants)
