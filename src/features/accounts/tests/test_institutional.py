from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from features.accounts.forms import SignUpForm
from features.users_manager.models import Organization, School, InstitutionalContact, OrganizationMembership
from features.users_manager.permissions import can_manage_organization

User = get_user_model()


class InstitutionalAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='platform', system_role='SYSADMIN', is_staff=True)
        self.owner = User.objects.create_user(username='schoolowner')
        self.organization = Organization.objects.create(name='Escola existente', owner=self.owner)
        self.school = School.objects.create(organization=self.organization, legal_name='Escola existente',
            display_name='Escola existente', school_type='PRIVATE', city='João Pessoa', state='PB',
            address='Rua da Escola, 10', inep_code='12345', approved_by=self.admin)

    def signup_data(self, role='STUDENT', code=None):
        return {'username': 'newperson', 'email': 'new@example.com', 'password1': 'Uncommon-pass-314159!',
                'password2': 'Uncommon-pass-314159!', 'registration_role': role,
                'institutional_code': self.school.institutional_code if code is None else code}

    def contact_data(self):
        return {'institution_name': 'Nova Escola', 'contact_name': 'Maria Silva', 'email': 'contato@example.com',
                'phone': '83999999999', 'city': 'João Pessoa', 'state': 'PB', 'message': 'Gostaria de cadastrar minha escola.'}

    def test_contact_is_public_persisted_and_does_not_create_school(self):
        url = reverse('accounts:institutional-contact')
        self.assertContains(self.client.get(url), 'Fale com a equipe')
        self.assertRedirects(self.client.post(url, self.contact_data()), url)
        self.assertEqual(InstitutionalContact.objects.count(), 1)
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)
        self.client.post(url, self.contact_data())
        self.assertEqual(InstitutionalContact.objects.count(), 1)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_contact_csrf_and_validation(self):
        url = reverse('accounts:institutional-contact')
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, self.contact_data()).status_code, 403)
        data = self.contact_data()
        data['email'] = 'bad'
        self.client.post(url, data)
        self.assertFalse(InstitutionalContact.objects.exists())
        data = self.contact_data()
        data['website'] = 'bot.example'
        self.client.post(url, data)
        self.assertFalse(InstitutionalContact.objects.exists())

    def test_student_signup_adds_context_without_management(self):
        response = self.client.post(reverse('accounts:sign-up'), self.signup_data(code=' '+self.school.institutional_code.lower()+' '))
        self.assertRedirects(response, reverse('accounts:onboarding'))
        user = User.objects.get(username='newperson')
        membership = OrganizationMembership.objects.get(user=user)
        self.assertEqual(membership.organization, self.organization)
        self.assertTrue(membership.is_student)
        self.assertFalse(membership.is_teacher)
        self.assertFalse(can_manage_organization(user, self.organization))
        self.assertFalse(user.is_staff)
        self.assertEqual(user.system_role, 'MEMBER')
        self.assertEqual(user.onboarding_role, 'STUDENT')

    def test_teacher_signup(self):
        self.client.post(reverse('accounts:sign-up'), self.signup_data('TEACHER'))
        member = OrganizationMembership.objects.get(user__username='newperson')
        self.assertTrue(member.is_teacher)
        self.assertFalse(member.is_student)
        self.assertFalse(member.user.is_system_admin)

    def test_invalid_disabled_and_inactive_codes_create_no_accounts(self):
        url = reverse('accounts:sign-up')
        for code in ['', 'LUM-INVALID']:
            self.assertEqual(self.client.post(url, self.signup_data(code=code)).status_code, 200)
            self.assertFalse(User.objects.filter(username='newperson').exists())
        self.school.registration_enabled = False
        self.school.save()
        self.client.post(url, self.signup_data())
        self.assertFalse(User.objects.filter(username='newperson').exists())
        self.school.registration_enabled = True
        self.school.save()
        self.organization.is_active = False
        self.organization.save()
        self.client.post(url, self.signup_data())
        self.assertFalse(User.objects.filter(username='newperson').exists())

    def test_personal_signup_still_available(self):
        self.client.post(reverse('accounts:sign-up'), self.signup_data('PERSONAL', code=''))
        self.assertTrue(User.objects.filter(username='newperson').exists())
        self.assertFalse(OrganizationMembership.objects.exists())

    def test_role_tampering_and_personal_with_code_rejected(self):
        for role in ['SYSADMIN', 'MANAGER', 'PERSONAL']:
            self.client.post(reverse('accounts:sign-up'), self.signup_data(role))
            self.assertFalse(User.objects.filter(username='newperson').exists())

    def test_code_revalidated_and_account_creation_rolls_back(self):
        form = SignUpForm(self.signup_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.school.registration_enabled = False
        self.school.save()
        with self.assertRaises(ValidationError):
            form.save()
        self.assertFalse(User.objects.filter(username='newperson').exists())
        self.school.registration_enabled = True
        self.school.save()
        with patch('features.accounts.forms.attach_membership', side_effect=ValidationError('Vínculo indisponível.')):
            with self.assertRaises(ValidationError):
                form.save()
        self.assertFalse(User.objects.filter(username='newperson').exists())

    def test_admin_can_register_school_from_contact_and_rotate_code(self):
        contact = InstitutionalContact.objects.create(**self.contact_data())
        self.client.force_login(self.admin)
        url = reverse('admin:users_manager_school_add')
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {'contact': contact.pk, 'organization_owner': self.owner.pk,
            'legal_name': 'Nova Escola LTDA', 'display_name': 'Nova Escola', 'school_type': 'PRIVATE',
            'cnpj': '', 'inep_code': '98765', 'address': 'Rua 2', 'city': 'João Pessoa', 'state': 'PB',
            'registration_enabled': 'on', '_save': 'Salvar'})
        self.assertEqual(response.status_code, 302)
        school = School.objects.get(inep_code='98765')
        self.assertEqual(school.organization.owner, self.owner)
        self.assertEqual(school.approved_by, self.admin)
        self.assertNotEqual(school.institutional_code, self.school.institutional_code)
        contact.refresh_from_db()
        self.assertEqual(contact.school, school)
        self.assertEqual(contact.status, 'COMPLETED')
        self.assertContains(self.client.get(reverse('admin:users_manager_school_change', args=[school.pk])), school.institutional_code)
        old = school.institutional_code
        self.client.post(reverse('admin:users_manager_school_changelist'), {'action': 'regenerate_codes', '_selected_action': [school.pk]})
        school.refresh_from_db()
        self.assertNotEqual(old, school.institutional_code)
        self.assertEqual(self.client.post(reverse('admin:users_manager_school_change', args=[school.pk]), {'_save': 'Salvar'}).status_code, 302)
        school.refresh_from_db()
        self.assertFalse(school.registration_enabled)

    def test_non_sysadmin_staff_cannot_read_contacts_or_codes_or_create_school(self):
        staff = User.objects.create_superuser(username='staff', email='staff@example.com', password='safe-test-pass')
        self.client.force_login(staff)  # Superuser alone is not the platform SYSADMIN role.
        for url in [reverse('admin:users_manager_school_add'),
                    reverse('admin:users_manager_school_change', args=[self.school.pk]),
                    reverse('admin:users_manager_institutionalcontact_changelist')]:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('admin:users_manager_school_add'), {}).status_code, 403)
