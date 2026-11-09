from django import forms
from .models import Question, AlternativeLegend
import copy


class AlternativesWidget(forms.Textarea):
    template_name = 'assessments/widgets/alternatives.html'

    def __init__(self, legends=()):
        self.legends = list(legends)
        super().__init__(attrs={'data-alternatives-input': '', 'hidden': True})


    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['legends'] = self.legends
        return context


class QuestionTypeMixin:
    def configure_question_type(self, source=None):
        current = self.instance if self.instance.pk else source
        metadata = (current.diagnostic_metadata or {}).get('alternatives', {}) if current else {}
        initial = [{'text': option, 'correct': option == current.correct_answer, 'legend': metadata.get('ABCDE'[index], {}).get('hypothesis', '')} for index, option in enumerate(current.options)] if current else []
        owner = getattr(self, 'sharing_owner', None)
        legends = AlternativeLegend.objects.filter(owner=owner).values_list('text', flat=True) if owner else []
        self.fields['options'].widget = forms.HiddenInput()
        self.fields['correct_answer'].widget = forms.HiddenInput()
        self.fields['answer_lines'].required = False
        self.fields['answer_lines'].widget.attrs.update({'min': '1', 'max': '40', 'step': '1'})
        self.fields['answer_lines'].help_text = 'Na impressão, cada linha terá 7 mm de altura.'
        if current and not self.is_bound:
            self.initial.setdefault('answer_lines', current.answer_lines)
        self.fields['question_type'].choices = [('multiple_choice', 'Fechada'), ('open_ended', 'Discursiva')]
        self.fields['alternatives'] = forms.JSONField(label='Alternativas', required=False,
            widget=AlternativesWidget(legends), initial=initial)
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
            self.instance.diagnostic_metadata['alternatives'] = {}
            return cleaned
        rows = cleaned.get('alternatives')
        if not isinstance(rows, list) or not 2 <= len(rows) <= 5:
            self.add_error('alternatives', 'Adicione de duas a cinco alternativas.')
            return cleaned
        if any(not isinstance(row, dict) or not isinstance(row.get('text'), str) or not row['text'].strip()
               or len(row['text']) > 10000 or not isinstance(row.get('correct'), bool) for row in rows):
            self.add_error('alternatives', 'Preencha o texto e marque cada alternativa como correta ou errada.')
            return cleaned
        if any(not isinstance(row.get('legend', ''), str) or len(row.get('legend', '').strip()) > 500 for row in rows):
            self.add_error('alternatives', 'Cada legenda deve ser um texto de até 500 caracteres.')
            return cleaned
        texts = [row['text'].strip() for row in rows]
        if len(set(texts)) != len(texts):
            self.add_error('alternatives', 'As alternativas devem ter textos diferentes.')
        if sum(row['correct'] for row in rows) != 1:
            self.add_error('alternatives', 'Marque exatamente uma alternativa correta.')
        # Rebuild by the submitted row, so deleting/reordering options never shifts a legend.
        old = self.instance.diagnostic_metadata.get('alternatives', {})
        old_options = list(self.instance.options or [])
        metadata = {}
        for index, row in enumerate(rows):
            original = old_options.index(row['text'].strip()) if row['text'].strip() in old_options else None
            details = copy.deepcopy(old.get('ABCDE'[original], {})) if original is not None else {}
            if 'legend' in row:
                legend = row['legend'].strip()
                details['hypothesis'] = legend
                details['reviewed'] = bool(legend)
            if any(details.values()):
                metadata['ABCDE'[index]] = details
        self.instance.diagnostic_metadata['alternatives'] = metadata
        cleaned['options'] = texts
        cleaned['correct_answer'] = next((row['text'].strip() for row in rows if row['correct']), '')
        return cleaned

    def save_alternative_legends(self, owner):
        for details in self.instance.diagnostic_metadata.get('alternatives', {}).values():
            text = details.get('hypothesis', '').strip()
            if text:
                AlternativeLegend.objects.get_or_create(owner=owner, text=text)
