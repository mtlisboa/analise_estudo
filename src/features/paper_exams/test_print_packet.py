from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase
from pypdf import PdfReader

from .documents import application_print_pdf, exam_pdf


class PrintPacketTests(SimpleTestCase):
    def make_run(self, count):
        question = {'statement': 'Questão de exemplo', 'points': '1',
            'type': 'multiple_choice', 'options': ['Um', 'Dois'],
            'correct': 'A', 'content_blocks': []}
        variants = {version: [dict(question)] for version in 'ABC'}
        sheets = [SimpleNamespace(pk=uuid4(), student_id=index + 1,
            student_name=f'Aluno {index + 1}', student_registration=str(index + 1),
            variant='ABC'[index % 3], questions=variants['ABC'[index % 3]])
            for index in range(count)]
        run = SimpleNamespace(title='Avaliação', classroom_name='Turma 1',
            context={'teacher': 'Professor Teste'}, created_by='Professor Teste',
            variants=variants, questions=[question], sheets=SimpleNamespace(all=lambda: sheets))
        return run, sheets

    def test_packet_orders_individual_sheets_then_balanced_versions_and_covers(self):
        run, _ = self.make_run(4)
        pages = [page.extract_text() for page in PdfReader(BytesIO(application_print_pdf([run]))).pages]
        self.assertEqual(len(pages), 11)
        for index in range(4):
            self.assertIn('Folha de respostas', pages[index])
            self.assertIn(f'Aluno {index + 1}', pages[index])
            self.assertIn('Professor Teste', pages[index])
        self.assertIn('Prova A', pages[4])
        self.assertIn('Prova A', pages[5])
        self.assertIn('CAPA - PROVA A', pages[6])
        self.assertIn('Prova B', pages[7])
        self.assertIn('CAPA - PROVA B', pages[8])
        self.assertIn('Prova C', pages[9])
        self.assertIn('CAPA - PROVA C', pages[10])
        self.assertNotIn('Folha de respostas', ''.join(pages[4:]))

    def test_exact_division_and_repeated_generation_preserve_assignment(self):
        run, sheets = self.make_run(6)
        before = [(sheet.pk, sheet.variant) for sheet in sheets]
        first = [p.extract_text() for p in PdfReader(BytesIO(application_print_pdf([run]))).pages]
        second = [p.extract_text() for p in PdfReader(BytesIO(application_print_pdf([run]))).pages]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 15)
        self.assertEqual(before, [(sheet.pk, sheet.variant) for sheet in sheets])
        for index, version in ((8, 'A'), (11, 'B'), (14, 'C')):
            self.assertIn(f'CAPA - PROVA {version}', first[index])
            self.assertIn('2 cadernos', first[index])

    def test_student_booklet_contains_only_assigned_questions(self):
        run, sheets = self.make_run(3)
        pages = [p.extract_text() for p in PdfReader(BytesIO(
            exam_pdf(run, [sheets[1]], include_answer_sheet=False))).pages]
        self.assertEqual(len(pages), 1)
        self.assertIn('Prova B', pages[0])
        self.assertIn('Aluno 2', pages[0])
        self.assertNotIn('Folha de respostas', pages[0])

    def test_every_student_has_exactly_one_identified_booklet(self):
        for count in (4, 10, 11):
            with self.subTest(count=count):
                run, sheets = self.make_run(count)
                pages = [p.extract_text() for p in PdfReader(BytesIO(application_print_pdf([run]))).pages]
                booklets = [text for text in pages if 'Questão 1' in text]
                self.assertEqual(len(booklets), count)
                for sheet in sheets:
                    own = [text for text in booklets
                           if f'Aluno ID {sheet.student_id}\n' in text]
                    self.assertEqual(len(own), 1)
                    self.assertIn(f'Prova {sheet.variant}', own[0])
                self.assertEqual(len(pages), count * 2 + 3)
