from django.core.exceptions import PermissionDenied
from django.test import TestCase

from . import tests as fixtures
from .application import ApplicationForm
from .services import authorize_teacher
from features.users_manager.models import ClassroomMembership


class ApplicationMembershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)

    def test_membership_does_not_require_published_schedule_or_matching_subject(self):
        self.period.published_at = None
        self.period.save(update_fields=['published_at'])
        self.offer.published_schedule = []
        self.offer.save(update_fields=['published_schedule'])
        self.assessment.subject = 'Outra disciplina'
        form = ApplicationForm(self.teacher, self.assessment)
        self.assertIn(self.offer, form.fields['offers'].queryset)
        authorize_teacher(self.teacher, self.offer, self.assessment.subject)

    def test_removed_membership_is_not_allowed(self):
        ClassroomMembership.objects.filter(
            classroom=self.classroom, user=self.teacher.user).update(status='REMOVED')
        self.assertNotIn(self.offer, ApplicationForm(
            self.teacher, self.assessment).fields['offers'].queryset)
        with self.assertRaises(PermissionDenied):
            authorize_teacher(self.teacher, self.offer, self.assessment.subject)

    def test_inactive_classroom_is_not_allowed(self):
        self.classroom.is_active = False
        self.classroom.save(update_fields=['is_active'])
        self.assertNotIn(self.offer, ApplicationForm(
            self.teacher, self.assessment).fields['offers'].queryset)

    def test_student_membership_does_not_grant_teacher_access(self):
        ClassroomMembership.objects.filter(
            classroom=self.classroom, user=self.teacher.user).update(role='STUDENT')
        self.assertNotIn(self.offer, ApplicationForm(
            self.teacher, self.assessment).fields['offers'].queryset)
        with self.assertRaises(PermissionDenied):
            authorize_teacher(self.teacher, self.offer, self.assessment.subject)
