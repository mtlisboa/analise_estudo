from django import forms
from django.contrib.auth import get_user_model

from .models import InstitutionalContact, School

STATES = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()


class InstitutionalContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    state = forms.ChoiceField(label='UF', choices=[('', 'Selecione')] + [(s, s) for s in STATES])

    class Meta:
        model = InstitutionalContact
        fields = ('institution_name', 'contact_name', 'email', 'phone', 'city', 'state', 'message')
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
            'contact_name': forms.TextInput(attrs={'autocomplete': 'name'}),
        }

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError('Não foi possível enviar o contato.')
        return ''

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class SchoolRegistrationAdminForm(forms.ModelForm):
    contact = forms.ModelChoiceField(label='Contato de origem', queryset=InstitutionalContact.objects.filter(school__isnull=True), required=False)
    organization_owner = forms.ModelChoiceField(
        label='Responsável pela organização', queryset=get_user_model().objects.filter(is_active=True),
        required=False, help_text='Escolha uma conta existente. Se ficar vazio, a organização ficará sob sua gestão até você transferi-la.')
    state = forms.ChoiceField(label='UF', choices=[('', 'Selecione')] + [(s, s) for s in STATES])

    class Meta:
        model = School
        fields = ('legal_name', 'display_name', 'school_type', 'cnpj', 'inep_code',
                  'address', 'city', 'state', 'registration_enabled')

    def clean(self):
        data = super().clean()
        if not data.get('cnpj') and not data.get('inep_code'):
            self.add_error('cnpj', 'Informe o CNPJ ou o código INEP da instituição.')
        return data

    def clean_cnpj(self):
        return (self.cleaned_data.get('cnpj') or '').strip() or None

    def clean_inep_code(self):
        return (self.cleaned_data.get('inep_code') or '').strip() or None
