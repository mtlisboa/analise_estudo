import csv
import io
import zipfile
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from features.assessments.models import Assessment, AssessmentTechnique, Question
from features.users_manager.models import Organization, Classroom, ClassroomMembership, ClassroomGroup
from features.paper_exams.documents import answer_sheets_pdf, exam_pdf, bubble_position
from features.paper_exams.models import SheetResult
from features.paper_exams.omr import read_page, ReadError
from features.paper_exams.services import issue_run, csv_template, process_upload, pages


class PaperExamTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.teacher = User.objects.create_user(username='teacher')
        self.student = User.objects.create_user(username='aluno001', first_name='João', last_name='da Silva')
        self.other = User.objects.create_user(username='other')
        organization = Organization.objects.create(name='Escola', owner=self.teacher)
        group = ClassroomGroup.objects.create(name='Fundamental', organization=organization, created_by=self.teacher)
        self.classroom = Classroom.objects.create(name='Turma 9A', organization=organization, owner=self.teacher, group=group)
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.student,
            role='STUDENT', status='ACTIVE', invited_by=self.teacher)
        technique = AssessmentTechnique.objects.first()
        self.assessment = Assessment.objects.create(owner=self.teacher, subject='Matemática', topic='Frações', technique=technique)
        for i in range(3):
            Question.objects.create(assessment=self.assessment, statement=f'Questão {i+1}: qual é a resposta?',
                                   options=['Um', 'Dois', 'Três', 'Quatro', 'Cinco'], correct_answer='Dois', points='2.50', order=i+1)
        self.run = issue_run(self.assessment, self.classroom, self.teacher)
        self.sheet = self.run.sheets.get()

    def upload(self, data, name='respostas.csv', run=None):
        return process_upload(run or self.run, self.teacher, SimpleUploadedFile(name, data))

    def filled_csv(self, answers, student=None):
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['sheet_id', 'student_id', 'q1', 'q2', 'q3'])
        writer.writerow([self.sheet.pk, student or self.student.pk] + answers)
        return output.getvalue().encode()

    def test_snapshot_survives_edits(self):
        self.assessment.questions.update(correct_answer='Um', statement='Alterada')
        self.upload(self.filled_csv(['B', 'A', '']))
        result = SheetResult.objects.get()
        self.assertEqual(result.score, Decimal('2.50'))
        self.assertEqual(result.maximum_score, Decimal('7.50'))
        self.assertIn('Questão 1', self.run.questions[0]['statement'])

    def test_csv_duplicate_invalid_and_wrong_student(self):
        bad = self.upload(self.filled_csv(['AB', 'B', 'B']))
        self.assertTrue(bad.errors)
        wrong = self.upload(self.filled_csv(['B', 'B', 'B'], self.other.pk))
        self.assertTrue(wrong.errors)
        self.assertEqual(SheetResult.objects.count(), 0)
        self.upload(self.filled_csv(['B', 'B', 'B']))
        duplicate = self.upload(self.filled_csv(['A', 'A', 'A']))
        self.assertTrue(duplicate.errors)
        self.assertEqual(SheetResult.objects.get().score, Decimal('7.50'))

    def test_csv_template_utf8_semicolon_and_blank(self):
        data = csv_template(self.run).replace(',', ';').encode('utf-8')
        batch = self.upload(data)
        self.assertEqual(batch.errors, [])
        self.assertEqual(SheetResult.objects.get().score, 0)

    def test_unauthorized_pages_and_evidence(self):
        self.upload(self.filled_csv(['B', 'B', 'B']))
        result = SheetResult.objects.get()
        routes = [reverse('paper-exams:index', args=[self.assessment.pk]),
                  reverse('paper-exams:detail', args=[self.run.pk]),
                  reverse('paper-exams:download', args=[self.run.pk, 'folhas']),
                  reverse('paper-exams:review', args=[result.pk]),
                  reverse('paper-exams:evidence', args=[result.pk])]
        for route in routes:
            self.assertEqual(self.client.get(route).status_code, 302)
        self.client.force_login(self.other)
        for route in routes:
            self.assertEqual(self.client.get(route).status_code, 404)

    def test_pages_and_review(self):
        self.upload(self.filled_csv(['B', 'A', '']))
        result = SheetResult.objects.get()
        self.client.force_login(self.teacher)
        for url in [reverse('paper-exams:index', args=[self.assessment.pk]),
                    reverse('paper-exams:detail', args=[self.run.pk]),
                    reverse('paper-exams:review', args=[result.pk])]:
            self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(reverse('paper-exams:review', args=[result.pk]),
                                    {'q1': 'B', 'q2': 'B', 'q3': '-', 'note': 'Conferido na folha original.'})
        self.assertEqual(response.status_code, 302)
        result.refresh_from_db()
        self.assertEqual(result.score, Decimal('5'))
        self.assertEqual(result.detected, ['B', 'A', ''])
        self.assertEqual(result.reviewed_by, self.teacher)

    def image(self):
        data = answer_sheets_pdf(self.run)
        return next(iter(pages(data, '.pdf')))[1]

    def mark(self, image, index, option, radius=5):
        # pages renders at min(3,2400/height); infer scale from raster dimensions.
        from features.paper_exams.documents import WIDTH
        scale = image.shape[1] / WIDTH
        x, y = bubble_position(index, option)
        cv2.circle(image, (round(x*scale), round(y*scale)), round(radius*scale), 0, -1)

    def test_pdf_omr_rotation_perspective_and_double_marks(self):
        image = self.image()
        self.mark(image, 0, 1)
        self.mark(image, 1, 0)
        self.mark(image, 1, 1)
        identity, answers, issues, evidence = read_page(image, self.run.questions)
        self.assertEqual(identity['student'], self.student.pk)
        self.assertEqual(answers, ['B', '?', ''])
        self.assertEqual(len(issues), 1)
        for rotation in (1, 2, 3):
            self.assertEqual(read_page(np.rot90(image, rotation).copy(), self.run.questions)[1], answers)
        h, w = image.shape
        transform = cv2.getPerspectiveTransform(np.float32([[0,0],[w,0],[w,h],[0,h]]),
            np.float32([[35,55],[w-70,10],[w-20,h-30],[60,h-60]]))
        skewed = cv2.warpPerspective(image, transform, (w,h), borderValue=255)
        self.assertEqual(read_page(skewed, self.run.questions)[1], answers)
        _, png = cv2.imencode('.png', image)
        batch = self.upload(png.tobytes(), 'folha.png')
        self.assertEqual(batch.errors, [])
        result = SheetResult.objects.get()
        self.assertEqual(result.status, 'review')
        self.assertIsNone(result.score)
        self.assertTrue(result.evidence)

    def test_pdf_roundtrip_blank_and_exam(self):
        batch = self.upload(answer_sheets_pdf(self.run), 'folhas.pdf')
        self.assertEqual(batch.errors, [])
        self.assertEqual(SheetResult.objects.get().answers, ['', '', ''])
        self.assertTrue(exam_pdf(self.run).startswith(b'%PDF'))

    def test_wrong_run_and_unreadable_image(self):
        another = issue_run(self.assessment, self.classroom, self.teacher)
        batch = self.upload(answer_sheets_pdf(self.run), 'folhas.pdf', run=another)
        self.assertTrue(batch.errors)
        self.assertEqual(SheetResult.objects.count(), 0)
        with self.assertRaises(ReadError):
            read_page(np.full((1000, 700), 255, np.uint8), self.run.questions)

    def test_zip_traversal_and_valid_import(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('../folha.pdf', answer_sheets_pdf(self.run))
        self.assertTrue(self.upload(buf.getvalue(), 'lote.zip').errors)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('turma/folha.pdf', answer_sheets_pdf(self.run))
        self.assertEqual(self.upload(buf.getvalue(), 'lote.zip').errors, [])
        self.assertEqual(SheetResult.objects.count(), 1)

    def test_invalid_exam_and_permissions(self):
        with self.assertRaises(ValidationError):
            issue_run(self.assessment, self.classroom, self.other)
        self.assessment.questions.update(question_type='open_ended')
        with self.assertRaises(ValidationError):
            issue_run(self.assessment, self.classroom, self.teacher)

    def test_full_sheet_all_columns_and_many_qr_payloads(self):
        self.assessment.questions.all().delete()
        for i in range(50):
            Question.objects.create(assessment=self.assessment, statement=f'Questão {i+1}',
                options=['Um', 'Dois', 'Três', 'Quatro', 'Cinco'], correct_answer='Dois', order=i+1)
        self.run = issue_run(self.assessment, self.classroom, self.teacher)
        image = self.image()
        for i in range(50):
            self.mark(image, i, i % 5)
        self.assertEqual(read_page(image, self.run.questions)[1], ['ABCDE'[i % 5] for i in range(50)])
        # Vary the UUID and signature: different QR patterns must be readable.
        for _ in range(12):
            self.run = issue_run(self.assessment, self.classroom, self.teacher)
            self.assertEqual(read_page(self.image(), self.run.questions)[1], ['']*50)

    def test_uncertain_marks_and_invalid_qr_never_grade(self):
        from unittest.mock import patch
        image = self.image()
        self.mark(image, 0, 0, radius=2)
        self.assertEqual(read_page(image, self.run.questions)[1][0], '?')
        with patch('features.paper_exams.documents.qr_payload', return_value='1:123:forged:signature'):
            image = self.image()
        with self.assertRaises(ReadError):
            read_page(image, self.run.questions)

    def test_review_history_preserves_multiple_changes(self):
        self.upload(self.filled_csv(['A', 'A', 'A']))
        result = SheetResult.objects.get()
        self.client.force_login(self.teacher)
        url = reverse('paper-exams:review', args=[result.pk])
        for answer in ['B', 'A']:
            self.assertEqual(self.client.post(url, {'q1': answer, 'q2': 'B', 'q3': 'B', 'note': 'Conferência.'}).status_code, 302)
        result.refresh_from_db()
        self.assertEqual(result.reviews.count(), 2)
        self.assertEqual(result.detected, ['A', 'A', 'A'])
        self.assertEqual(result.reviews.first().previous_answers, ['B', 'B', 'B'])
