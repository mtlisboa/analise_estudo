from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import InstitutionalContact, School, InstitutionalAccount
from features.accounts.institutional import normalize_domain, normalize_registration, available_email

STATES = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()


class InstitutionalContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)
    state = forms.ChoiceField(label='UF', choices=[('', 'Selecione')] + [(s, s) for s in STATES])

    class Meta:
        model = InstitutionalContact
        fields = ('institution_name', 'contact_name', 'email', 'phone', 'city', 'state', 'message')
        widgets = {'message': forms.Textarea(attrs={'rows': 4})}

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError('Não foi possível enviar o contato.')
        return ''

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class TemporaryPasswordForm(forms.Form):
    password = forms.CharField(label='Senha provisória', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password_confirm = forms.CharField(label='Confirmar senha provisória', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('password_confirm'):
            self.add_error('password_confirm', 'As senhas não conferem.')
        if data.get('password'):
            try:
                validate_password(data['password'])
            except ValidationError as exc:
                self.add_error('password', exc)
        return data


class InstitutionalUserForm(TemporaryPasswordForm):
    registration = forms.CharField(label='Matrícula / registro', max_length=40)
    first_name = forms.CharField(label='Nome', max_length=150)
    last_name = forms.CharField(label='Sobrenome', max_length=150, required=False)
    role = forms.ChoiceField(label='Perfil', choices=[choice for choice in InstitutionalAccount.Role.choices if choice[0] != 'ADMIN'])
    field_order = ['registration', 'first_name', 'last_name', 'role', 'password', 'password_confirm']

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields['registration'].help_text = f'O acesso será registro@{organization.school.email_domain}.'

    def clean_registration(self):
        registration = normalize_registration(self.cleaned_data['registration'])
        if self.organization.institutional_accounts.filter(registration=registration).exists():
            raise ValidationError('Este registro já existe na instituição.')
        available_email(f'{registration}@{self.organization.school.email_domain}')
        return registration


class InstitutionAdministratorForm(TemporaryPasswordForm):
    domain = forms.CharField(label='Domínio institucional', max_length=100, help_text='Ex.: escola.edu.br. Define os identificadores de login, sem criar caixas postais.')
    registration = forms.CharField(label='Identificação do administrativo', max_length=40, initial='administrativo')
    first_name = forms.CharField(label='Nome do responsável administrativo', max_length=150)
    last_name = forms.CharField(label='Sobrenome', max_length=150, required=False)
    field_order = ['domain', 'registration', 'first_name', 'last_name', 'password', 'password_confirm']

    def clean_domain(self):
        return normalize_domain(self.cleaned_data['domain'])

    def clean_registration(self):
        return normalize_registration(self.cleaned_data['registration'])

    def clean(self):
        data = super().clean()
        if data.get('domain') and data.get('registration'):
            available_email(f"{data['registration']}@{data['domain']}")
        return data


class SchoolRegistrationAdminForm(TemporaryPasswordForm, forms.ModelForm):
    contact = forms.ModelChoiceField(label='Contato de origem', queryset=InstitutionalContact.objects.filter(school__isnull=True), required=False)
    admin_registration = forms.CharField(label='Identificação do administrativo', max_length=40, initial='administrativo', help_text='O e-mail será identificação@domínio informado.')
    admin_name = forms.CharField(label='Nome do responsável administrativo', max_length=150)
    email_domain = forms.CharField(label='Domínio institucional', max_length=100, help_text='Ex.: escola.edu.br. Não cria caixas postais externas.')
    state = forms.ChoiceField(label='UF', choices=[('', 'Selecione')] + [(s, s) for s in STATES])

    class Meta:
        model = School
        fields = ('legal_name', 'display_name', 'school_type', 'cnpj', 'inep_code', 'address', 'city', 'state', 'email_domain')

    def clean_email_domain(self):
        domain = normalize_domain(self.cleaned_data['email_domain'])
        if School.objects.filter(email_domain__iexact=domain).exists():
            raise ValidationError('Este domínio já está em uso por outra instituição.')
        return domain

    def clean_admin_registration(self):
        return normalize_registration(self.cleaned_data['admin_registration'])

    def clean(self):
        data = super().clean()
        if not data.get('cnpj') and not data.get('inep_code'):
            self.add_error('cnpj', 'Informe o CNPJ ou o código INEP da instituição.')
        if data.get('email_domain') and data.get('admin_registration'):
            email = available_email(f"{data['admin_registration']}@{data['email_domain']}")
            if data.get('password'):
                validate_password(data['password'], get_user_model()(username=email, email=email, first_name=data.get('admin_name', '')))
        return data

    def clean_cnpj(self):
        return (self.cleaned_data.get('cnpj') or '').strip() or None

    def clean_inep_code(self):
        return (self.cleaned_data.get('inep_code') or '').strip() or None
