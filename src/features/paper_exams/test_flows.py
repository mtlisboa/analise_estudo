import io
from pathlib import Path
from decimal import Decimal

import cv2
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader

from . import tests as fixtures
from .models import SheetResult, ScanPage
from .services import issue_run, pages, process_upload
from .documents import exam_pdf, bubble_position
from .omr import page_identity
from features.assessments.models import Question


class PrintedFlowTests(TestCase):
    def setUp(self):
        fixtures.PaperExamTests.setUp(self)
        Question.objects.create(assessment=self.assessment, order=4, question_type='open_ended',
            statement='Explique como chegou à resposta.', correct_answer='REFERÊNCIA PRIVADA', points=2)
        self.run = issue_run(self.assessment, self.classroom, self.teacher)
        self.sheet = self.run.sheets.get()

    def test_mixed_booklet_qr_camera_association_omr_and_manual_score(self):
        pdf = exam_pdf(self.run)
        Path('/tmp/flow-sample.pdf').write_bytes(pdf)
        document = PdfReader(io.BytesIO(pdf))
        self.assertGreaterEqual(len(document.pages), 2)
        text = '\n'.join(p.extract_text() for p in document.pages)
        for expected in ['João da Silva','Turno','Sala','Explique como']:
            self.assertIn(expected, text)
        self.assertNotIn('REFERÊNCIA PRIVADA',text)
        rendered = list(pages(pdf,'.pdf'))
        self.client.force_login(self.teacher)
        for number,image in reversed(rendered):
            identity = page_identity(image)
            self.assertEqual(identity['student'],self.student.pk)
            if number == 1:
                # Render scale is 2400/HEIGHT; convert known PDF-point centers.
                scale = image.shape[0]/841.8897637795277
                for i in range(3):
                    x,y = bubble_position(i,1)
                    cv2.circle(image,(round(x*scale),round(y*scale)),round(5*scale),0,-1)
            ok,png = cv2.imencode('.png', image)
            response = self.client.post(reverse('paper-exams:scan'), {'file':SimpleUploadedFile('foto.png',png.tobytes(),content_type='image/png')})
            self.assertEqual(response.status_code,302, response.content[:3000])
        result = SheetResult.objects.get(sheet=self.sheet)
        self.assertEqual(result.answers[:3],['B','B','B'])
        self.assertEqual(result.status,'review')
        self.assertIsNone(result.score)
        self.assertEqual(ScanPage.objects.filter(sheet=self.sheet).count(),len(rendered)-1)
        url = reverse('paper-exams:review',args=[result.pk])
        data = {'q1':'B','q2':'B','q3':'B','open4':'1.5','note':'Resposta conferida na foto.'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        result.refresh_from_db()
        self.assertEqual(result.score,Decimal('9.00'))
        self.assertEqual(result.status,'graded')
        self.assertEqual(result.reviews.get().open_scores,{'4':'1.5'})
        self.assertEqual(self.client.get(reverse('paper-exams:download',args=[self.run.pk,'provas'])+f'?student={self.other.pk}').status_code,404)

    def test_camera_denies_foreign_teacher_and_keeps_duplicate(self):
        image = list(pages(exam_pdf(self.run),'.pdf'))[1][1]
        _,png=cv2.imencode('.png',image)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('paper-exams:scan'), {'file':SimpleUploadedFile('foto.png',png.tobytes())}).status_code,404)
        self.assertFalse(ScanPage.objects.exists())
        self.client.force_login(self.teacher)
        for expected in [302,200]:
            self.assertEqual(self.client.post(reverse('paper-exams:scan'), {'file':SimpleUploadedFile('foto.png',png.tobytes())}).status_code,expected)
        self.assertEqual(ScanPage.objects.count(),1)

    def test_open_only_is_not_automatically_graded_zero(self):
        self.assessment.questions.exclude(question_type='open_ended').delete()
        run=issue_run(self.assessment,self.classroom,self.teacher)
        batch=process_upload(run,self.teacher,SimpleUploadedFile('prova.pdf',exam_pdf(run)))
        self.assertEqual(batch.errors,[])
        self.assertIsNone(batch.results.get().score)
        self.assertEqual(batch.results.get().status,'review')
