from datetime import date

from django.urls import reverse
from django.utils import timezone

from contexts.institutions.planning.models import Offer, Period
from features.users_manager.models import ClassroomMembership
from .test_institutional_contexts import InstitutionalContextTests


class StudentPortalTests(InstitutionalContextTests):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.period = Period.objects.create(organization=cls.organization, name='2026',
            starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), published_at=timezone.now())
        cls.offer = Offer.objects.create(period=cls.period, name='Turma própria', grade='1',
            shift='MORNING', capacity=30, classroom=cls.classroom,
            published_schedule=[{'subject': 'MATEMÁTICA', 'teacher': 'Professora publicada',
                'teacher_id': 1, 'day': 1, 'weekday': 'Segunda', 'start': '08:00', 'end': '09:00',
                'period_start': '2026-01-01', 'period_end': '2026-12-31',
                'classroom': 'Turma própria', 'period': '2026', 'code': 'published-code'}])
        cls.hidden = Offer.objects.create(period=cls.period, name='Sem matrícula', grade='1',
            shift='MORNING', capacity=30, classroom=cls.other_classroom,
            published_schedule=[{**cls.offer.published_schedule[0], 'subject': 'DISCIPLINA PRIVADA'}])

    def test_portal_and_subject_detail_use_published_enrolled_schedule(self):
        self.client.force_login(self.users['STUDENT'])
        response = self.client.get(reverse('institutions:aluno'))
        self.assertContains(response, 'MATEMÁTICA')
        self.assertTemplateUsed(response, 'components/layout/student_navigation.html')
        response = self.client.get(reverse('institutions:student-disciplines'))
        self.assertContains(response, 'Professora publicada')
        self.assertNotContains(response, 'DISCIPLINA PRIVADA')
        detail = reverse('institutions:student-discipline', args=[self.offer.code, 'MATEMÁTICA'])
        self.assertContains(self.client.get(detail), '08:00–09:00')
        self.assertContains(self.client.get(detail), '01/01/2026')
        self.assertNotContains(self.client.get(reverse('institutions:student-disciplines'), {'q': 'biologia'}), 'Professora publicada')
        self.assertContains(self.client.get(reverse('institutions:student-disciplines'), {'q': 'matemática'}), 'Professora publicada')
        self.assertEqual(self.client.post(detail).status_code, 405)

    def test_direct_urls_cannot_bypass_enrolment_or_publication(self):
        self.client.force_login(self.users['STUDENT'])
        url = reverse('institutions:student-discipline', args=[self.hidden.code, 'DISCIPLINA PRIVADA'])
        self.assertEqual(self.client.get(url).status_code, 404)
        url = reverse('institutions:student-discipline', args=[self.offer.code, 'MATEMÁTICA'])
        ClassroomMembership.objects.filter(user=self.users['STUDENT']).update(status='REMOVED')
        self.assertEqual(self.client.get(url).status_code, 404)
        ClassroomMembership.objects.filter(user=self.users['STUDENT']).update(status='ACTIVE')
        self.period.published_at = None
        self.period.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_other_roles_cannot_enter_student_subjects(self):
        for role in ('ADMIN', 'MANAGER', 'TEACHER', 'OPERATOR', 'GUARDIAN'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(reverse('institutions:student-disciplines')).status_code, 403)

    def test_inactive_institution_and_classroom_revoke_access(self):
        self.client.force_login(self.users['STUDENT'])
        url = reverse('institutions:student-discipline', args=[self.offer.code, 'MATEMÁTICA'])
        self.classroom.is_active = False
        self.classroom.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.organization.is_active = False
        self.organization.save()
        url = reverse('institutions:student-disciplines')
        self.assertRedirects(self.client.get(url), reverse('accounts:login') + '?next=' + url, fetch_redirect_response=False)
