from django import forms
from django.core.exceptions import ValidationError


def validate_metadata(value):
    if not isinstance(value, dict) or set(value) - {'skills','alternatives'}:
        raise ValidationError('Use um objeto com skills e alternatives.')
    skills = value.get('skills', [])
    alternatives = value.get('alternatives', {})
    if not isinstance(skills, list) or any(not isinstance(s,str) or not s.strip() or len(s)>80 for s in skills):
        raise ValidationError('Habilidades devem ser uma lista de códigos de até 80 caracteres.')
    if not isinstance(alternatives, dict):
        raise ValidationError('Alternativas devem ser um objeto por letra.')
    for letter, meta in alternatives.items():
        if letter not in 'ABCDE' or len(letter)!=1 or not isinstance(meta,dict):
            raise ValidationError('Identifique cada alternativa por A, B, C, D ou E.')
        if set(meta)-{'justification','hypothesis','skill','reviewed'} or any(not isinstance(meta.get(k,''),str) for k in ('justification','hypothesis','skill')) or not isinstance(meta.get('reviewed',False),bool):
            raise ValidationError('Metadados inválidos: textos e reviewed booleano.')

def validate_tags(value):
    if not isinstance(value, list) or len(value) > 100 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 200 for item in value):
        raise ValidationError('Use até 100 metadados, com até 200 caracteres por item.')


class DiagnosticFields:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta = self.instance.diagnostic_metadata or {}
        self.fields['skill_codes'] = forms.CharField(label='Habilidades BNCC / objetivos locais', required=False,
            help_text='Códigos separados por vírgula; identificação curricular não comprova domínio.', initial=', '.join(meta.get('skills', [])))
        self.fields['metadata_text'] = forms.CharField(label='Metadados', required=False, max_length=20000,
            widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'frações; interpretação de gráficos; aplicação no cotidiano'}),
            help_text='Palavras ou pequenas sentenças separadas por ponto e vírgula (;).',
            initial='; '.join(self.instance.metadata_tags or []))

    def clean(self):
        import copy
        data = super().clean()
        tags = list(dict.fromkeys(text.strip() for text in data.get('metadata_text', '').split(';') if text.strip()))
        try:
            validate_tags(tags)
        except ValidationError as exc:
            self.add_error('metadata_text', exc)
        self.instance.metadata_tags = tags
        alternatives = copy.deepcopy((self.instance.diagnostic_metadata or {}).get('alternatives', {}))
        # Preserve historical classifications and legacy API payloads without rendering their controls.
        for letter in 'ABCDE'[:len(data.get('options', []))]:
            keys = ('justification', 'hypothesis', 'skill', 'reviewed')
            if any(f'diagnostic_{letter}_{key}' in self.data for key in keys):
                row = {key: str(self.data.get(f'diagnostic_{letter}_{key}', '')).strip()[:500] for key in keys[:-1]}
                row['reviewed'] = str(self.data.get(f'diagnostic_{letter}_reviewed', '')).lower() in ('on', 'true', '1')
                if any(row.values()):
                    alternatives[letter] = row
                else:
                    alternatives.pop(letter, None)
        metadata = {'skills': list(dict.fromkeys(x.strip() for x in data.get('skill_codes', '').split(',') if x.strip())),
            'alternatives': alternatives}
        validate_metadata(metadata)
        self.instance.diagnostic_metadata = metadata
        return data
