from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from reportlab.pdfgen.canvas import Canvas

from features.users_manager.models import ClassroomMembership
from .models import PDFModule
from . import tests as fixtures


class SubjectModulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)

    def upload(self):
        stream = BytesIO()
        canvas = Canvas(stream)
        canvas.drawString(30, 700, 'Material de estudo')
        canvas.save()
        return SimpleUploadedFile('aula.pdf', stream.getvalue(), content_type='application/pdf')

    def test_teacher_publishes_student_opens_and_removed_member_is_denied(self):
        self.client.force_login(self.teacher.user)
        response = self.client.post(reverse('coursework:pdf-create', args=[self.offer.code, 'MATEMÁTICA']),
            {'title': 'Leitura inicial', 'document': self.upload()})
        self.assertEqual(response.status_code, 302)
        pdf = PDFModule.objects.get()
        self.client.force_login(self.student.user)
        room = self.client.get(response.url)
        self.assertContains(room, 'Leitura inicial')
        opened = self.client.get(reverse('coursework:pdf-open', args=[pdf.pk]))
        self.assertEqual(opened['Content-Type'], 'application/pdf')
        self.assertTrue(b''.join(opened.streaming_content).startswith(b'%PDF-'))
        self.assertEqual(self.client.post(reverse('coursework:pdf-remove', args=[pdf.pk])).status_code, 404)
        ClassroomMembership.objects.filter(user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.client.get(reverse('coursework:pdf-open', args=[pdf.pk])).status_code, 403)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(reverse('coursework:pdf-remove', args=[pdf.pk])).status_code, 302)
        self.assertFalse(PDFModule.objects.exists())

    def test_invalid_upload_and_unassigned_subject_are_rejected(self):
        self.client.force_login(self.teacher.user)
        url = reverse('coursework:pdf-create', args=[self.offer.code, 'MATEMÁTICA'])
        response = self.client.post(url, {'title': 'Inválido', 'document': SimpleUploadedFile('fake.pdf', b'%PDF-fake')})
        self.assertContains(response, 'Envie um PDF válido')
        self.assertFalse(PDFModule.objects.exists())
        self.assertEqual(self.client.get(reverse('coursework:pdf-create', args=[self.offer.code, 'HISTÓRIA'])).status_code, 403)
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_subject_rooms_isolate_modules_and_teacher_assignment(self):
        self.offer.published_schedule.append({'subject': 'HISTÓRIA', 'teacher_id': self.admin.institutional_account.pk})
        self.offer.save()
        PDFModule.objects.create(offer=self.offer, subject='HISTÓRIA', teacher=self.teacher, title='Material histórico', document=b'')
        self.client.force_login(self.student.user)
        url = reverse('institutions:classroom', args=[self.classroom.pk])
        self.assertContains(self.client.get(url), 'Escolha a sala de uma disciplina')
        response = self.client.get(url, {'subject': 'MATEMÁTICA'})
        self.assertNotContains(response, 'Material histórico')
        self.assertContains(self.client.get(url, {'subject': 'HISTÓRIA'}), 'Material histórico')
        self.assertEqual(self.client.get(url, {'subject': 'INVALID'}).status_code, 404)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.get(url, {'subject': 'HISTÓRIA'}).status_code, 404)
        self.assertNotContains(self.client.get(reverse('institutions:classrooms')), 'HISTÓRIA')
