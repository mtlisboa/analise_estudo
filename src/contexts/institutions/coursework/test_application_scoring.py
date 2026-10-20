from decimal import Decimal
from datetime import timedelta
import uuid
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from .tests import CourseworkTests
from .application import ApplicationForm
from .services import publish
from features.assessments.application_scoring import application_points
from features.paper_exams.services import issue_run


class ApplicationScoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CourseworkTests.setUpTestData.__func__(cls)

    def test_virtual_snapshot_preserves_application_score_and_original_question(self):
        self.publication.application_metadata = {
            'total_points': '7.50', 'question_points': {str(self.question.pk): '7.50'}}
        self.publication.save()
        publish(self.teacher, self.publication, prepare_only=True)
        self.publication.refresh_from_db()
        self.question.refresh_from_db()
        self.assertEqual(self.publication.public_snapshot['questions'][0]['points'], '7.50')
        self.assertEqual(self.publication.grading_snapshot[0]['points'], '7.50')
        self.assertEqual(self.publication.public_snapshot['total_points'], '7.50')
        self.assertEqual(self.question.points, Decimal('2'))

    def test_print_snapshot_preserves_application_score(self):
        run = issue_run(self.assessment, self.classroom, self.teacher.user,
                        question_points={str(self.question.pk): '6.25'})
        self.assertEqual(run.questions[0]['points'], '6.25')
        self.question.refresh_from_db()
        self.assertEqual(self.question.points, Decimal('2'))

    def test_form_rejects_total_that_does_not_match_questions(self):
        form = ApplicationForm(self.teacher, self.assessment, data={
            'request_token': str(uuid.uuid4()), 'kind': 'EXAM', 'title': 'Pontuação',
            'offers': [self.offer.pk], 'delivery_mode': 'online',
            'due_at': (timezone.now() + timedelta(days=1)).isoformat(),
            'total_points': '10', f'points_{self.question.pk}': '4'})
        self.assertFalse(form.is_valid())
        self.assertIn('total_points', form.errors)

    def test_invalid_values_and_changed_question_set_are_rejected(self):
        for value in ('NaN', 'Infinity', '0', '-1', '1.001'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                application_points([self.question], {str(self.question.pk): value})
        with self.assertRaises(ValidationError):
            application_points([self.question], {})
