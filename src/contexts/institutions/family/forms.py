from django import forms
from features.users_manager.models import Classroom, InstitutionalAccount
from .models import GuardianLink, FamilyRequest, SchoolEvent


class LinkForm(forms.ModelForm):
    class Meta:
        model = GuardianLink
        fields = ['guardian', 'student', 'relationship', 'is_active']

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = InstitutionalAccount.objects.filter(organization=account.organization, user__is_active=True)
        self.fields['guardian'].queryset = accounts.filter(role='GUARDIAN')
        self.fields['student'].queryset = accounts.filter(role='STUDENT')


class RequestForm(forms.ModelForm):
    class Meta:
        model = FamilyRequest
        fields = ['student', 'title', 'description']

    def __init__(self, *args, children, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = children
        self.fields['student'].label = 'Filho(a)'
        self.fields['student'].required = self.instance.kind == 'DOCUMENT'


class ReplyForm(forms.Form):
    text = forms.CharField(label='Mensagem', max_length=3000, widget=forms.Textarea)
    attachment = forms.FileField(label='Documento PDF (até 10 MB)', required=False)
    status = forms.ChoiceField(label='Situação', choices=FamilyRequest.Status.choices)

    def clean_attachment(self):
        file = self.cleaned_data.get('attachment')
        if file:
            if file.size > 10 * 1024 * 1024 or not file.name.lower().endswith('.pdf') or file.read(5) != b'%PDF-':
                raise forms.ValidationError('Envie um PDF válido de até 10 MB.')
            file.seek(0)
        return file


class EventForm(forms.ModelForm):
    class Meta:
        model = SchoolEvent
        fields = ['classroom', 'title', 'description', 'starts_at', 'ends_at', 'location', 'is_published']
        widgets = {name: forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
                   for name in ('starts_at', 'ends_at')}

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classroom'].queryset = Classroom.objects.filter(organization=account.organization, is_active=True)
        self.fields['classroom'].empty_label = 'Toda a instituição'


class PerformanceFilterForm(forms.Form):
    starts_on = forms.DateField(label='De', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ends_on = forms.DateField(label='Até', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    subject = forms.CharField(label='Disciplina', required=False, max_length=120)

    def clean(self):
        data = super().clean()
        if data.get('starts_on') and data.get('ends_on') and data['starts_on'] > data['ends_on']:
            raise forms.ValidationError('O início deve ser igual ou anterior ao fim.')
        return data
