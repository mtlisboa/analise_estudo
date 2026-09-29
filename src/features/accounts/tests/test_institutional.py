from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from features.accounts.institutional import provision_administrator, provision_member, reset_institutional_password
from features.accounts.forms import ProfileForm
from features.users_manager.models import Organization, School, InstitutionalContact, InstitutionalAccount, OrganizationMembership

User = get_user_model()
TEMP = 'Random-initial!73926'
PERSONAL = 'New-private-secret!93018'


class InstitutionalAccessTests(TestCase):
    def setUp(self):
        self.platform = User.objects.create_user(username='platform', system_role='SYSADMIN', is_staff=True)
        self.organization = Organization.objects.create(name='Escola', owner=self.platform)
        self.school = School.objects.create(organization=self.organization, legal_name='Escola', display_name='Escola',
            school_type='PRIVATE', city='João Pessoa', state='PB', address='Rua 10', inep_code='12345', approved_by=self.platform)
        self.administrator = provision_administrator(self.organization, self.platform, domain='escola.edu.br',
            registration='administrativo', password=TEMP, first_name='Maria')
        self.admin = self.administrator.user
        self.admin.must_change_password = False
        self.admin.onboarding_completed_at = timezone.now()
        self.admin.save()
        self.organization.refresh_from_db()

    def member(self, registration='2026001', role='STUDENT'):
        return provision_member(self.organization, self.admin, registration=registration, role=role, password=TEMP, first_name='João')

    def contact_data(self):
        return {'institution_name': 'Nova Escola', 'contact_name': 'Maria Silva', 'email': 'contato@example.com',
                'phone': '83999999999', 'city': 'João Pessoa', 'state': 'PB', 'message': 'Quero cadastrar a escola.'}

    def test_contact_remains_public_and_does_not_create_accounts(self):
        url = reverse('accounts:institutional-contact')
        self.assertContains(self.client.get(url), 'Fale com a equipe')
        self.assertRedirects(self.client.post(url, self.contact_data()), url)
        self.assertEqual(InstitutionalContact.objects.count(), 1)
        self.assertEqual(School.objects.count(), 1)
        self.client.post(url, self.contact_data())
        self.assertEqual(InstitutionalContact.objects.count(), 1)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, self.contact_data()).status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_admin_creation_assigns_contextual_management_only(self):
        self.assertEqual(self.organization.owner, self.admin)
        self.assertEqual(self.administrator.email, 'administrativo@escola.edu.br')
        self.assertFalse(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(self.admin.system_role, 'MEMBER')
        self.assertTrue(self.admin.check_password(TEMP))
        with self.assertRaises(ValidationError):
            provision_administrator(self.organization, self.platform, domain='escola.edu.br', registration='second', password=TEMP)

    def test_student_teacher_registration_and_no_elevation(self):
        student = self.member()
        teacher = self.member('prof123', 'TEACHER')
        self.assertEqual(student.email, '2026001@escola.edu.br')
        self.assertTrue(OrganizationMembership.objects.get(user=student.user).is_student)
        self.assertTrue(OrganizationMembership.objects.get(user=teacher.user).is_teacher)
        self.assertTrue(student.user.must_change_password)
        self.assertFalse(student.user.is_staff)
        self.assertNotEqual(self.organization.owner_id, teacher.user_id)
        with self.assertRaises(ValidationError):
            self.member('fake-admin', 'ADMIN')

    def test_registration_duplicate_collision_and_no_user_takeover(self):
        self.member()
        with self.assertRaises(ValidationError):
            self.member()
        User.objects.create_user(username='legacy', email='Taken@escola.edu.br', password=PERSONAL)
        with self.assertRaises(ValidationError):
            self.member('taken')
        self.assertTrue(User.objects.get(username='legacy').check_password(PERSONAL))
        for registration in ['a@other.com', 'x y', 'á', '../evil']:
            with self.assertRaises(ValidationError):
                self.member(registration)
        self.assertEqual(InstitutionalAccount.objects.count(), 2)

    def test_login_by_email_and_required_new_password(self):
        identity = self.member()
        response = self.client.post(reverse('accounts:login'), {'username': identity.email.upper(), 'password': TEMP})
        self.assertRedirects(response, reverse('accounts:institutional-password'))
        for url in [reverse('accounts:account'), reverse('accounts:dashboard'), reverse('assessments:index')]:
            self.assertRedirects(self.client.get(url), reverse('accounts:institutional-password'))
        url = reverse('accounts:institutional-password')
        self.assertContains(self.client.post(url, {'new_password1': TEMP, 'new_password2': TEMP}), 'diferente da provisória')
        response = self.client.post(url, {'new_password1': PERSONAL, 'new_password2': PERSONAL})
        self.assertEqual(response.status_code, 302)
        identity.user.refresh_from_db()
        self.assertFalse(identity.user.must_change_password)
        self.assertTrue(identity.user.check_password(PERSONAL))
        self.assertFalse(identity.user.check_password(TEMP))
        self.assertEqual(self.client.get(reverse('accounts:account')).status_code, 200)

    def test_admin_member_page_and_form(self):
        self.client.force_login(self.admin)
        url = reverse('users-manager:institutional-accounts', args=[self.organization.pk])
        self.assertContains(self.client.get(url), 'Cadastrar acesso institucional')
        response = self.client.post(url, {'registration': '2026002', 'first_name': 'Ana', 'last_name': 'Silva',
            'role': 'TEACHER', 'password': TEMP, 'password_confirm': TEMP})
        self.assertRedirects(response, url)
        self.assertTrue(InstitutionalAccount.objects.filter(email='2026002@escola.edu.br', role='TEACHER').exists())
        self.assertNotContains(response, TEMP, status_code=302)

    def test_tenant_isolation_and_student_cannot_manage(self):
        identity = self.member()
        identity.user.must_change_password = False
        identity.user.save()
        self.client.force_login(identity.user)
        url = reverse('users-manager:institutional-accounts', args=[self.organization.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        other = Organization.objects.create(name='Other', owner=self.platform)
        School.objects.create(organization=other, legal_name='Other', display_name='Other', school_type='PUBLIC',
            city='Recife', state='PE', address='Rua', approved_by=self.platform)
        self.client.force_login(self.admin)
        other_url = reverse('users-manager:institutional-accounts', args=[other.pk])
        self.assertEqual(self.client.get(other_url).status_code, 403)
        self.assertEqual(self.client.post(other_url, {}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            provision_member(other, self.admin, registration='a', role='STUDENT', password=TEMP)

    def test_password_reset_invalidates_session_and_requires_change(self):
        identity = self.member()
        identity.user.must_change_password = False
        identity.user.save()
        self.client.force_login(identity.user)
        reset_institutional_password(identity, self.admin, PERSONAL)
        self.assertEqual(self.client.get(reverse('accounts:account')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
        identity.user.refresh_from_db()
        self.assertTrue(identity.user.must_change_password)
        self.assertTrue(identity.user.check_password(PERSONAL))
        with self.assertRaises(PermissionDenied):
            reset_institutional_password(self.administrator, self.admin, TEMP)

    def test_inactive_organization_denies_login_and_session(self):
        self.client.force_login(self.admin)
        self.organization.is_active = False
        self.organization.save()
        self.assertEqual(self.client.get(reverse('accounts:account')).status_code, 302)
        self.assertFalse(self.client.login(username=self.administrator.email, password=TEMP))

    def test_legacy_personal_signup_login_still_works_and_code_does_not(self):
        data = {'username': 'personal', 'email': 'personal@example.com', 'password1': TEMP, 'password2': TEMP}
        self.client.post(reverse('accounts:sign-up'), dict(data, institutional_code='LUM-OLD'))
        self.assertFalse(User.objects.filter(username='personal').exists())
        self.client.post(reverse('accounts:sign-up'), dict(data, email='guess@escola.edu.br'))
        self.assertFalse(User.objects.filter(username='personal').exists())
        self.assertEqual(self.client.post(reverse('accounts:sign-up'), data).status_code, 302)
        self.client.logout()
        self.assertTrue(self.client.login(username='personal', password=TEMP))
        self.client.logout()
        self.assertTrue(self.client.login(username='personal@example.com', password=TEMP))
        self.assertEqual(InstitutionalAccount.objects.count(), 1)

    def test_managed_user_cannot_change_email_or_username(self):
        identity = self.member()
        form = ProfileForm({'username': 'hijacked', 'email': 'hijacked@example.com', 'first_name': 'João',
                            'last_name': 'Silva', 'current_password': TEMP}, instance=identity.user)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, identity.email)
        self.assertEqual(user.username, identity.email)

    def test_admin_school_creation_creates_login_and_connects_contact(self):
        contact = InstitutionalContact.objects.create(**self.contact_data())
        self.client.force_login(self.platform)
        response = self.client.post(reverse('admin:users_manager_school_add'), {
            'contact': contact.pk, 'legal_name': 'Nova Escola LTDA', 'display_name': 'Nova Escola',
            'school_type': 'PRIVATE', 'inep_code': '98765', 'address': 'Rua 2', 'city': 'João Pessoa', 'state': 'PB',
            'email_domain': 'nova.edu.br', 'admin_registration': 'administrativo', 'admin_name': 'Carlos',
            'password': TEMP, 'password_confirm': TEMP, '_save': 'Salvar'})
        self.assertEqual(response.status_code, 302)
        school = School.objects.get(inep_code='98765')
        self.assertEqual(school.organization.owner.email, 'administrativo@nova.edu.br')
        self.assertTrue(school.organization.owner.must_change_password)
        contact.refresh_from_db()
        self.assertEqual(contact.school, school)
        self.assertEqual(self.client.get(reverse('admin:users_manager_school_change', args=[school.pk])).status_code, 200)

    def test_non_sysadmin_cannot_create_institution_or_administrator(self):
        staff = User.objects.create_superuser(username='staff', email='staff@example.com', password=TEMP)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('admin:users_manager_school_add')).status_code, 403)
        with self.assertRaises(PermissionDenied):
            provision_administrator(self.organization, self.admin, domain='escola.edu.br', registration='newadmin', password=TEMP)
