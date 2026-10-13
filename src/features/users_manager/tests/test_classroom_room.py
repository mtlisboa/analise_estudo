from datetime import timedelta
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from contexts.institutions.coursework.models import Publication
from contexts.institutions.coursework.services import publish
from features.notifications.models import Notification
from features.users_manager.models import ClassroomNotice, ClassroomMembership


class ClassroomRoomTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from contexts.institutions.coursework.tests import CourseworkTests
        CourseworkTests.setUpTestData.__func__(cls)

    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.url = reverse('institutions:classroom', args=[self.classroom.pk])
        self.client.force_login(self.teacher.user)

    def image(self):
        stream = BytesIO()
        Image.new('RGB', (640, 240), 'green').save(stream, 'PNG')
        return SimpleUploadedFile('sala.png', stream.getvalue(), content_type='image/png')

    def test_teacher_edits_cover_and_student_reads_private_cover(self):
        response = self.client.post(reverse('users-manager:classroom-cover-update', args=[self.classroom.pk]),
            {'image': self.image(), 'description': 'Imagem da turma'})
        self.assertEqual(response.status_code, 302)
        self.classroom.refresh_from_db()
        self.assertTrue(self.classroom.cover_image)
        self.client.force_login(self.student.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'Imagem da turma')
        self.assertContains(response, 'class="classroom-context"')
        self.assertTemplateNotUsed(response, 'components/layout/sidebar.html')
        self.assertNotContains(response, 'Espaço da turma')
        self.assertNotContains(response, 'Editar imagem da sala')
        response = self.client.get(reverse('users-manager:classroom-cover', args=[self.classroom.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(self.client.post(reverse('users-manager:classroom-cover-update', args=[self.classroom.pk]),
            {'remove':'on'}).status_code, 403)
        self.classroom.refresh_from_db()
        self.assertTrue(self.classroom.cover_image)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(reverse('users-manager:classroom-cover-update', args=[self.classroom.pk]),
            {'remove':'on'}).status_code, 302)
        self.classroom.refresh_from_db()
        self.assertFalse(self.classroom.cover_image)

    def test_invalid_image_is_rejected_without_replacing_cover(self):
        response = self.client.post(reverse('users-manager:classroom-cover-update', args=[self.classroom.pk]),
            {'image': SimpleUploadedFile('fake.png', b'not an image')})
        self.assertEqual(response.status_code, 422)
        self.classroom.refresh_from_db()
        self.assertFalse(self.classroom.cover_image)

    def test_notice_hub_populates_summary_and_notifies_only_active_members(self):
        Notification.objects.all().delete()
        response = self.client.post(reverse('users-manager:classroom-notice-create', args=[self.classroom.pk]),
            {'title':'Aviso da sala', 'body':'Levar material amanhã.'})
        self.assertEqual(response.status_code, 302)
        notice = ClassroomNotice.objects.get(classroom=self.classroom)
        self.assertEqual(notice.author, self.teacher.user)
        self.assertEqual(list(Notification.objects.values_list('recipient_id', flat=True)), [self.student.user_id])
        self.client.force_login(self.student.user)
        self.assertContains(self.client.get(self.url), 'Aviso da sala', count=2)
        self.assertEqual(self.client.post(reverse('users-manager:classroom-notice-create', args=[self.classroom.pk]),
            {'title':'Indevido', 'body':'texto'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('users-manager:classroom-notice-withdraw', args=[self.classroom.pk,notice.pk])).status_code, 403)
        self.client.force_login(self.teacher.user)
        self.assertEqual(self.client.post(reverse('users-manager:classroom-notice-withdraw', args=[self.classroom.pk,notice.pk])).status_code, 302)
        self.assertNotContains(self.client.get(self.url), 'Aviso da sala')

    def test_offer_directories_and_available_exams_precede_activities(self):
        self.publication.due_at = timezone.now() + timedelta(days=1)
        self.publication.save()
        publish(self.teacher, self.publication)
        draft = Publication.objects.create(offer=self.offer, subject='MATEMÁTICA', teacher=self.teacher,
            assessment=self.assessment, kind='EXAM', title='PROVA SECRETA')
        expired = Publication.objects.create(offer=self.offer, subject='MATEMÁTICA', teacher=self.teacher,
            assessment=self.assessment, kind='EXAM', title='Prova encerrada', due_at=timezone.now()-timedelta(days=1))
        publish(self.teacher, expired)
        self.client.force_login(self.student.user)
        response = self.client.get(self.url)
        self.assertContains(response, str(self.offer.code))
        self.assertContains(response, 'Provas disponíveis')
        self.assertContains(response, 'Diretórios de atividades')
        self.assertNotContains(response, 'PROVA SECRETA')
        self.assertEqual([item['title'] for item in response.context['available_exams']], [self.publication.title])
        self.assertEqual(response.context['directories'][0]['name'], 'MATEMÁTICA')
        self.assertEqual(len(response.context['directories'][0]['items']), 2)
        self.assertLess(response.content.index(b'room-exams-title'),response.content.index(b'room-directories-title'))
        self.publication.title = 'Título do rascunho'
        self.publication.save()
        self.assertNotContains(self.client.get(self.url), 'Título do rascunho')

    def test_unrelated_or_removed_users_cannot_read_or_write_room(self):
        for role in ('GUARDIAN',):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.get(reverse('users-manager:classroom-cover', args=[self.classroom.pk])).status_code, 403)
        self.client.force_login(self.student.user)
        ClassroomMembership.objects.filter(classroom=self.classroom, user=self.student.user).update(status='REMOVED')
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_offer_filter_cannot_cross_classrooms_and_legacy_room_keeps_tests(self):
        self.assertEqual(self.client.get(self.url, {'offer':'not-an-offer'}).status_code, 404)
        response = self.client.get(reverse('institutions:classroom', args=[self.other_classroom.pk]))
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('institutions:classroom', args=[self.other_classroom.pk]))
        self.assertContains(response, 'Oferta ainda não publicada')
        self.assertContains(response, 'Registros de avaliação da turma')
