import re
from io import BytesIO
from django.test import SimpleTestCase
from pypdf import PdfReader
from . import test_print_packet as fixtures
from .documents import answer_sheets_pdf, application_print_pdf, exam_pdf


class AnswerSheetCompletenessTests(SimpleTestCase):
    def make_run(self, count, opened=False):
        run, sheets = fixtures.PrintPacketTests().make_run(1)
        questions = [{'id': i, 'statement': f'Pergunta {i}', 'points': '1',
            'type': 'open_ended' if opened and i > 1 else 'multiple_choice',
            'options': [] if opened and i > 1 else ['Um', 'Dois'],
            'answer_lines': 1, 'content_blocks': []} for i in range(1, count + 1)]
        run.questions = questions
        run.variants = {}
        for sheet in sheets:
            sheet.variant = ''
            sheet.questions = questions
        return run, sheets

    def test_all_four_closed_questions_have_numbered_rows(self):
        run, _ = self.make_run(4)
        text = PdfReader(BytesIO(answer_sheets_pdf(run))).pages[0].extract_text()
        for number in range(1, 5):
            self.assertRegex(text, rf'(?m)^{number:02}$')

    def test_open_questions_remain_visible_and_keep_original_numbering(self):
        run, _ = self.make_run(4, opened=True)
        text = PdfReader(BytesIO(answer_sheets_pdf(run))).pages[0].extract_text()
        for number in range(1, 5):
            self.assertRegex(text, rf'(?m)^{number:02}$')
        self.assertEqual(text.count('Discursiva: responda no caderno'), 3)

    def test_fifty_questions_are_present_across_both_columns(self):
        run, _ = self.make_run(50)
        text = PdfReader(BytesIO(answer_sheets_pdf(run))).pages[0].extract_text()
        for number in range(1, 51):
            self.assertRegex(text, rf'(?m)^{number:02}$')

    def test_without_answer_sheet_in_packet_and_individual_reprint(self):
        run, sheets = self.make_run(4)
        run.context['omit_answer_sheet'] = True
        for data in (application_print_pdf([run]), exam_pdf(run, sheets)):
            text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)
            self.assertNotIn('Folha de respostas', text)
            for number in range(1, 5):
                self.assertIn(f'Pergunta {number}', text)
