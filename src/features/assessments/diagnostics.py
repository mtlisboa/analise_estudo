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

class DiagnosticFields:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta = self.instance.diagnostic_metadata or {}
        self.fields['skill_codes'] = forms.CharField(label='Habilidades BNCC / objetivos locais', required=False,
            help_text='Códigos separados por vírgula; identificação curricular não comprova domínio.', initial=', '.join(meta.get('skills',[])))
        for letter in 'ABCDE':
            row = meta.get('alternatives',{}).get(letter,{})
            for key, label in [('justification','Justificativa pedagógica'),('hypothesis','Hipótese de erro'),('skill','Habilidade / conceito')]:
                self.fields[f'diagnostic_{letter}_{key}'] = forms.CharField(label=f'{letter} · {label}', required=False, max_length=500, initial=row.get(key,''))
            self.fields[f'diagnostic_{letter}_reviewed'] = forms.BooleanField(label=f'{letter} · Classificação revisada', required=False, initial=row.get('reviewed',False))
    def clean(self):
        data = super().clean()
        alternatives = {}
        for letter in 'ABCDE'[:len(data.get('options',[]))]:
            row = {key:data.get(f'diagnostic_{letter}_{key}',False if key=='reviewed' else '') for key in ('justification','hypothesis','skill','reviewed')}
            if any(row.values()): alternatives[letter] = row
        metadata = {'skills':list(dict.fromkeys(x.strip() for x in data.get('skill_codes','').split(',') if x.strip())), 'alternatives':alternatives}
        validate_metadata(metadata)
        self.instance.diagnostic_metadata = metadata
        return data
