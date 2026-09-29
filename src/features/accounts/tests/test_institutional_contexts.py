from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.institutional import provision_administrator, provision_member
from features.users_manager.models import (
    Classroom, ClassroomGroup, ClassroomMembership, ClassroomTest,
    InstitutionalAccount, Organization, OrganizationMembership, School,
)


class InstitutionalContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.platform = User.objects.create_user(username='platform', system_role='SYSADMIN')
        cls.organization = Organization.objects.create(name='Escola local', owner=cls.platform)
        School.objects.create(organization=cls.organization, legal_name='Escola local',
            display_name='Escola local', school_type='PRIVATE', city='João Pessoa',
            state='PB', address='Rua 1', approved_by=cls.platform)
        cls.admin = provision_administrator(cls.organization, cls.platform, domain='local.edu.br',
            registration='admin', password='Initial-secret!92837').user
        cls.organization.refresh_from_db()
        cls.users = {'ADMIN': cls.admin}
        for role in ('TEACHER', 'STUDENT', 'MANAGER', 'OPERATOR', 'GUARDIAN'):
            cls.users[role] = provision_member(cls.organization, cls.admin,
                registration=role.lower(), role=role, password='Initial-secret!92837',
                first_name=f'Pessoa {role}').user
        for user in cls.users.values():
            user.must_change_password = False
            user.onboarding_completed_at = timezone.now()
            user.save()
        group = ClassroomGroup.objects.create(name='Grupo', organization=cls.organization, created_by=cls.admin)
        cls.classroom = Classroom.objects.create(name='Turma própria', organization=cls.organization,
            group=group, owner=cls.admin)
        cls.other_classroom = Classroom.objects.create(name='Turma sem vínculo', organization=cls.organization,
            group=group, owner=cls.admin)
        for role in ('TEACHER', 'STUDENT'):
            ClassroomMembership.objects.create(classroom=cls.classroom, user=cls.users[role],
                role=role, status='ACTIVE', invited_by=cls.admin)
        for title, published in [('Prova publicada', True), ('Prova rascunho', False)]:
            ClassroomTest.objects.create(classroom=cls.classroom, title=title,
                is_published=published, created_by=cls.users['TEACHER'])
        cls.other = Organization.objects.create(name='Outra instituição', owner=cls.platform)
        School.objects.create(organization=cls.other, legal_name='Outra', display_name='Outra',
            school_type='PUBLIC', city='Recife', state='PE', address='Rua 2', approved_by=cls.platform)
        other_admin = provision_administrator(cls.other, cls.platform, domain='other.edu.br',
            registration='private-other', password='Initial-secret!92837', first_name='Pessoa externa')
        cls.other.refresh_from_db()
        other_group = ClassroomGroup.objects.create(name='Outro grupo', organization=cls.other, created_by=cls.platform)
        Classroom.objects.create(name='Turma externa', organization=cls.other, group=other_group, owner=other_admin.user)

    def test_role_routes_and_no_cross_role_access(self):
        routes = {'ADMIN': 'gestor', 'MANAGER': 'gestor', 'TEACHER': 'professor',
                  'STUDENT': 'aluno', 'OPERATOR': 'operador', 'GUARDIAN': 'responsavel'}
        for role, slug in routes.items():
            with self.subTest(role=role):
                self.client.force_login(self.users[role])
                url = reverse(f'institutions:{slug}')
                self.assertRedirects(self.client.get(reverse('institutions:index')), url)
                self.assertRedirects(self.client.get(reverse('accounts:dashboard')),
                    reverse('institutions:index'), fetch_redirect_response=False)
                response = self.client.get(url)
                self.assertContains(response, 'Escola local')
                self.assertTemplateUsed(response, 'components/layout/sidebar.html')
                self.assertTemplateUsed(response, 'notifications/bell.html')
                self.assertNotContains(response, 'Pessoa externa')
                self.assertNotContains(response, 'Turma externa')
                for other_slug in set(routes.values()) - {slug}:
                    self.assertEqual(self.client.get(reverse(f'institutions:{other_slug}')).status_code, 403)

    def test_educational_views_restrict_classes_and_drafts(self):
        for role, slug in [('STUDENT', 'aluno'), ('TEACHER', 'professor')]:
            self.client.force_login(self.users[role])
            response = self.client.get(reverse(f'institutions:{slug}'))
            self.assertContains(response, 'Turma própria')
            self.assertContains(response, 'Prova publicada')
            self.assertNotContains(response, 'Turma sem vínculo')
            if role == 'STUDENT':
                self.assertNotContains(response, 'Prova rascunho')
            else:
                self.assertContains(response, 'Prova rascunho')

    def test_new_profiles_do_not_gain_educational_or_admin_permissions(self):
        for role in ('MANAGER', 'OPERATOR', 'GUARDIAN'):
            user = self.users[role]
            self.assertFalse(OrganizationMembership.objects.filter(user=user).exists())
            self.assertEqual(user.system_role, 'MEMBER')
            self.assertFalse(user.is_staff)
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('users-manager:institutional-accounts',
                args=[self.organization.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                provision_member(self.organization, user, registration='forbidden',
                    role='MANAGER', password='Initial-secret!92837')

    def test_operator_search_is_scoped_and_read_only(self):
        self.client.force_login(self.users['OPERATOR'])
        url = reverse('institutions:operador')
        response = self.client.get(url, {'q': 'STUDENT', 'organization': self.other.pk})
        self.assertContains(response, 'Pessoa STUDENT')
        self.assertNotContains(response, 'Pessoa TEACHER')
        self.assertNotContains(response, 'Pessoa externa')
        self.assertEqual(self.client.post(url, {}).status_code, 405)

    def test_guardian_does_not_receive_unlinked_students(self):
        self.client.force_login(self.users['GUARDIAN'])
        response = self.client.get(reverse('institutions:responsavel'))
        self.assertNotContains(response, 'Pessoa STUDENT')
        self.assertNotContains(response, 'Prova publicada')
        self.assertContains(response, 'ainda não está disponível')

    def test_anonymous_personal_and_onboarding_roles_cannot_enter(self):
        self.assertEqual(self.client.get(reverse('institutions:index')).status_code, 302)
        user = get_user_model().objects.create_user(username='personal', onboarding_role='MANAGER',
            onboarding_completed_at=timezone.now())
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('institutions:gestor')).status_code, 403)
        self.assertEqual(self.client.get(reverse('accounts:dashboard')).status_code, 200)

    def test_database_role_change_takes_effect_without_new_login(self):
        self.client.force_login(self.users['OPERATOR'])
        InstitutionalAccount.objects.filter(user=self.users['OPERATOR']).update(role='GUARDIAN')
        self.assertEqual(self.client.get(reverse('institutions:operador')).status_code, 403)
        self.assertRedirects(self.client.get(reverse('institutions:index')), reverse('institutions:responsavel'))
