from django import forms
from .models import Question


class AlternativesWidget(forms.Textarea):
    template_name = 'assessments/widgets/alternatives.html'

    def __init__(self):
        super().__init__(attrs={'data-alternatives-input': '', 'rows': 4})


class QuestionTypeMixin:
    def configure_question_type(self, source=None):
        current = self.instance if self.instance.pk else source
        initial = [{'text': option, 'correct': option == current.correct_answer} for option in current.options] if current else []
        self.fields['answer_lines'].required = False
        self.fields['answer_lines'].widget.attrs.update({'min': '1', 'max': '40', 'step': '1'})
        self.fields['answer_lines'].help_text = 'Na impressão, cada linha terá 7 mm de altura.'
        if current and not self.is_bound:
            self.initial.setdefault('answer_lines', current.answer_lines)
        self.fields['question_type'].choices = [('multiple_choice', 'Fechada'), ('open_ended', 'Discursiva')]
        self.fields['alternatives'] = forms.JSONField(label='Alternativas', required=False,
            widget=AlternativesWidget(), initial=initial)
        order = list(self.fields)
        order.remove('alternatives')
        order.remove('answer_lines')
        index = order.index('question_type') + 1
        order[index:index] = ['alternatives', 'answer_lines']
        self.order_fields(order)

    def clean_question_type_fields(self, cleaned):
        if cleaned.get('answer_lines') is None:
            if 'alternatives' in self.data and cleaned.get('question_type') == Question.Type.OPEN_ENDED:
                self.add_error('answer_lines', 'Informe o número de linhas para a resposta.')
            else:
                cleaned['answer_lines'] = 6
        if 'alternatives' not in self.data:
            return cleaned
        if cleaned.get('question_type') == Question.Type.OPEN_ENDED:
            cleaned['options'] = []
            cleaned['correct_answer'] = ''
            return cleaned
        rows = cleaned.get('alternatives')
        if not isinstance(rows, list) or not 2 <= len(rows) <= 5:
            self.add_error('alternatives', 'Adicione de duas a cinco alternativas.')
            return cleaned
        if any(not isinstance(row, dict) or not isinstance(row.get('text'), str) or not row['text'].strip()
               or len(row['text']) > 10000 or not isinstance(row.get('correct'), bool) for row in rows):
            self.add_error('alternatives', 'Preencha o texto e marque cada alternativa como correta ou errada.')
            return cleaned
        texts = [row['text'].strip() for row in rows]
        if len(set(texts)) != len(texts):
            self.add_error('alternatives', 'As alternativas devem ter textos diferentes.')
        if sum(row['correct'] for row in rows) != 1:
            self.add_error('alternatives', 'Marque exatamente uma alternativa correta.')
        cleaned['options'] = texts
        cleaned['correct_answer'] = next((row['text'].strip() for row in rows if row['correct']), '')
        return cleaned
