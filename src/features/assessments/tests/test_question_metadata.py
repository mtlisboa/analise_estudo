from django.test import TestCase
from django.urls import reverse
from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.assessments.services import add_bank_item_to_assessment
from . import test_question_images as fixtures


class QuestionMetadataTests(TestCase):
    setUp = fixtures.QuestionImageTests.setUp
    data = fixtures.QuestionImageTests.data

    def test_new_fields_replace_per_alternative_diagnostic_controls(self):
        for form_class in (QuestionBankItemForm, QuestionForm):
            form = form_class()
            self.assertIn('assessment_method', form.fields)
            self.assertIn('metadata_text', form.fields)
            self.assertFalse(any(name.startswith('diagnostic_') for name in form.fields))
        response = self.client.get(reverse('assessments:bank-question-create'))
        self.assertContains(response, 'Método avaliativo')
        self.assertContains(response, 'Metadados')
        for label in ('Justificativa pedagógica', 'Hipótese de erro', 'Habilidade / conceito', 'Classificação revisada'):
            self.assertNotContains(response, label)

    def test_semicolon_metadata_is_normalized_saved_reopened_and_searchable(self):
        form = QuestionBankItemForm(self.data(assessment_method='Resolução de problemas',
            metadata_text='  frações ; interpretação de gráficos ; ; frações; aplicação no cotidiano  ;'))
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.user)
        item.refresh_from_db()
        self.assertEqual(item.assessment_method, 'Resolução de problemas')
        self.assertEqual(item.metadata_tags, ['frações', 'interpretação de gráficos', 'aplicação no cotidiano'])
        reopened = QuestionBankItemForm(instance=item)
        self.assertEqual(reopened['metadata_text'].value(), 'frações; interpretação de gráficos; aplicação no cotidiano')
        page = self.client.get(reverse('assessments:question-bank'), {'scope': 'private', 'q': 'aplicação no cotidiano'})
        self.assertContains(page, item.display_title)
        copied = add_bank_item_to_assessment(self.assessment, item)
        self.assertEqual(copied.metadata_tags, item.metadata_tags)
        self.assertEqual(copied.assessment_method, item.assessment_method)
        derived_form = QuestionBankItemForm(source=item)
        self.assertEqual(derived_form['metadata_text'].value(), reopened['metadata_text'].value())
        self.assertEqual(derived_form['assessment_method'].value(), item.assessment_method)

    def test_manual_assessment_question_preserves_fields_in_bank_copy(self):
        form = QuestionForm(self.data(assessment_method='Análise de caso', metadata_text='raciocínio; situação prática'))
        self.assertTrue(form.is_valid(), form.errors)
        question = form.save(self.assessment)
        self.assertEqual(question.metadata_tags, ['raciocínio', 'situação prática'])
        self.assertEqual(question.bank_item.metadata_tags, question.metadata_tags)
        self.assertEqual(question.bank_item.assessment_method, 'Análise de caso')

    def test_removed_controls_do_not_erase_historical_classifications(self):
        form = QuestionBankItemForm(self.data())
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save_for(self.user)
        original = {'B': {'hypothesis': 'Classificação anterior', 'reviewed': True}}
        item.diagnostic_metadata = {'skills': ['H1'], 'alternatives': original}
        item.save()
        edited = QuestionBankItemForm(self.data(skill_codes='H1', metadata_text='novo metadado'), instance=item)
        self.assertTrue(edited.is_valid(), edited.errors)
        self.assertEqual(edited.save_for(self.user).diagnostic_metadata['alternatives'], original)

    def test_metadata_item_length_is_validated(self):
        form = QuestionBankItemForm(self.data(metadata_text='x' * 201))
        self.assertFalse(form.is_valid())
        self.assertIn('metadata_text', form.errors)
