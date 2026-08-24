from django.core.management import call_command
from django.test import TestCase, override_settings

from features.accounts.models import User
from features.assessments.models import Assessment
from features.users_manager.models import Classroom, Organization, SelfAssessment


class SeedMockDataTests(TestCase):
    @override_settings(MOCK_MODE=False)
    def test_does_nothing_outside_mock_mode(self):
        call_command("seed_mock_data")
        self.assertFalse(User.objects.filter(username="demo").exists())

    @override_settings(MOCK_MODE=True, MOCK_USERNAME="demo", MOCK_PASSWORD="demo-password")
    def test_creates_complete_idempotent_demo(self):
        call_command("seed_mock_data")
        call_command("seed_mock_data")

        demo = User.objects.get(username="demo")
        self.assertTrue(demo.check_password("demo-password"))
        self.assertTrue(demo.has_completed_onboarding)
        self.assertEqual(Organization.objects.filter(owner=demo).count(), 2)
        self.assertEqual(Classroom.objects.filter(owner=demo).count(), 3)
        self.assertGreaterEqual(SelfAssessment.objects.count(), 10)
        self.assertEqual(Assessment.objects.filter(owner=demo).count(), 4)
