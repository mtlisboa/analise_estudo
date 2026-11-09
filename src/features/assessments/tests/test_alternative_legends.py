import json
from django.test import TestCase
from features.assessments.forms import QuestionBankItemForm, QuestionForm
from features.assessments.models import AlternativeLegend
from features.assessments.services import add_bank_item_to_assessment
from . import test_question_images as fixtures


class AlternativeLegendTests(TestCase):
    setUp = fixtures.QuestionImageTests.setUp
    data = fixtures.QuestionImageTests.data

    def rows(self):
        return [{'text':'Correta','correct':True,'legend':''},
                {'text':'Incorreta','correct':False,'legend':'Confunde numerador com denominador'}]

    def create(self, rows=None):
        form = QuestionBankItemForm(self.data(alternatives=json.dumps(rows or self.rows())), owner=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save_for(self.user)

    def test_register_select_reopen_copy_and_owner_catalog(self):
        item = self.create()
        self.assertEqual(AlternativeLegend.objects.filter(owner=self.user).count(),1)
        self.assertTrue(item.diagnostic_metadata['alternatives']['B']['reviewed'])
        reopened = QuestionBankItemForm(instance=item, owner=self.user)
        self.assertEqual(reopened.fields['alternatives'].initial[1]['legend'], self.rows()[1]['legend'])
        self.assertContains(self.client.get('/avaliacoes/questoes/nova/'), self.rows()[1]['legend'], status_code=200)
        other = QuestionBankItemForm(owner=self.other)
        self.assertEqual(other.fields['alternatives'].widget.legends, [])
        self.create()
        self.assertEqual(AlternativeLegend.objects.filter(owner=self.user).count(),1)
        copied = add_bank_item_to_assessment(self.assessment,item)
        self.assertEqual(copied.diagnostic_metadata,item.diagnostic_metadata)

    def test_reorder_and_remove_legend_follow_the_alternative(self):
        item = self.create()
        rows = list(reversed(self.rows()))
        form = QuestionBankItemForm(self.data(alternatives=json.dumps(rows)), instance=item, owner=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        updated = form.save_for(self.user)
        self.assertEqual(updated.diagnostic_metadata['alternatives']['A']['hypothesis'], rows[0]['legend'])
        self.assertNotIn('B',updated.diagnostic_metadata['alternatives'])
        rows[0]['legend']=''
        form = QuestionBankItemForm(self.data(alternatives=json.dumps(rows)), instance=updated, owner=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.save_for(self.user).diagnostic_metadata['alternatives'],{})

    def test_invalid_question_does_not_register_legend(self):
        rows = self.rows(); rows[0]['correct']=False
        form=QuestionBankItemForm(self.data(alternatives=json.dumps(rows)), owner=self.user)
        self.assertFalse(form.is_valid())
        self.assertFalse(AlternativeLegend.objects.exists())
        rows=self.rows();rows[1]['legend']='x'*501
        self.assertFalse(QuestionBankItemForm(self.data(alternatives=json.dumps(rows))).is_valid())

    def test_question_creation_registers_legends_and_open_question_clears_them(self):
        form=QuestionForm(self.data(alternatives=json.dumps(self.rows())),owner=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        question=form.save(self.assessment)
        self.assertEqual(question.diagnostic_metadata,question.bank_item.diagnostic_metadata)
        self.assertEqual(AlternativeLegend.objects.filter(owner=self.user).count(),1)
        form=QuestionBankItemForm(self.data(question_type='open_ended',alternatives='[]',answer_lines='6'),instance=question.bank_item,owner=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.save_for(self.user).diagnostic_metadata['alternatives'],{})

    def test_printed_shuffle_keeps_each_legend_attached_to_its_text(self):
        from features.paper_exams.variants import make_variants
        rows = [{'id':1, 'type':'multiple_choice','options':['Correta','Sinal','Conceito'],
                 'correct':'A','points':'1','diagnostic_metadata':{'alternatives':{
                     'B':{'hypothesis':'Erro de sinal','reviewed':True},
                     'C':{'hypothesis':'Confusão conceitual','reviewed':True}}}}]
        variants = make_variants(rows,'legend-test',shuffle_options=True)
        for questions in variants.values():
            question=questions[0]
            for letter, metadata in question['diagnostic_metadata']['alternatives'].items():
                text=question['options']['ABCDE'.index(letter)]
                self.assertEqual(metadata['hypothesis'], {'Sinal':'Erro de sinal','Conceito':'Confusão conceitual'}[text])
