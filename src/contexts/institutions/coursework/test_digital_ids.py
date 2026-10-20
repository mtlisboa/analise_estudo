from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from features.assessments.models import Question
from . import tests as fixtures
from .models import Submission
from .services import publish
from .submissions import AnswerForm, revision
from .digital import presentation


class DigitalIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.CourseworkTests.setUpTestData.__func__(cls)
        cls.objective = Question.objects.create(assessment=cls.assessment, order=2, statement='Selecione.',
            options=['Alternativa incorreta', 'Alternativa correta', 'Outro distrator'], correct_answer='Alternativa correta', points=3)

    def setUp(self):
        self.publication.application_metadata = {'virtual_shuffle_questions': True, 'virtual_shuffle_options': True}
        self.publication.save(update_fields=['application_metadata'])
        self.publication = publish(self.teacher, self.publication)
        self.client.force_login(self.student.user)

    def test_presentations_are_stable_and_keep_ids_with_shuffled_content(self):
        for student in range(1, 10):
            view = presentation(self.publication, student)
            self.assertEqual(view, presentation(self.publication, student))
            self.assertEqual({row['id'] for row in view['questions']}, {str(self.question.pk), str(self.objective.pk)})
            for row in view['questions']:
                original = next(q for q in self.publication.public_snapshot['questions'] if q['id'] == row['id'])
                self.assertEqual(dict(zip(row['option_ids'], row['options'])), dict(zip(original['option_ids'], original['options'])))
        patterns = {str(presentation(self.publication, student)['questions']) for student in range(1, 10)}
        self.assertGreater(len(patterns), 1)

    def test_submission_grades_by_question_and_option_ids_after_shuffling(self):
        data = {'revision': revision(self.publication)}
        for index, key in enumerate(self.publication.grading_snapshot):
            data[f'q{index+1}'] = key['correct_option_id'] if key['type'] == 'multiple_choice' else 'Uma parte do todo.'
        response = self.client.post(reverse('coursework:student-detail', args=[self.publication.pk]), data)
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get()
        self.assertEqual(submission.automatic_score, Decimal('3'))
        key = next(q for q in self.publication.grading_snapshot if q['type'] == 'multiple_choice')
        self.assertEqual(submission.answer_ids[str(self.objective.pk)], key['correct_option_id'])
        self.assertEqual(submission.answers['q2'], '1')

    def test_option_from_another_question_is_rejected(self):
        form = AnswerForm(self.publication, {'revision': revision(self.publication), 'q1':'Resposta',
            'q2': 'id-de-outra-questao'}, student_id=self.student.user_id)
        self.assertFalse(form.is_valid())
        self.assertIn('q2', form.errors)

    def test_identical_option_texts_do_not_make_the_wrong_id_correct(self):
        # Historical or imported content may contain identical labels: identity must decide.
        self.objective.options = ['Mesmo texto', 'Mesmo texto']
        self.objective.correct_answer = 'Mesmo texto'
        self.objective.save()
        self.publication = publish(self.teacher, self.publication)
        question = self.publication.public_snapshot['questions'][1]
        data = {'revision': revision(self.publication), 'q1':'Resposta aberta', 'q2':question['option_ids'][1]}
        response = self.client.post(reverse('coursework:student-detail', args=[self.publication.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.get().automatic_score, 0)
