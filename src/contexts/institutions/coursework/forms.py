from django import forms

from features.assessments.models import Assessment
from .models import Publication


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ['kind', 'title', 'instructions', 'due_at']
        widgets = {'due_at': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})}


class ExistingAssessmentForm(forms.Form):
    assessment = forms.ModelChoiceField(label='Avaliação já criada', queryset=Assessment.objects.none())

    def __init__(self, *args, account, subject, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assessment'].queryset = Assessment.objects.filter(owner=account.user, subject__iexact=subject)
