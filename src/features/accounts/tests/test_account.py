from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

class AccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='owner', email='owner@example.com', password='Old-password-8294!', onboarding_completed_at=timezone.now())
        self.other = User.objects.create_user(username='other', email='other@example.com', password='Other-password-8294!')
        self.client.force_login(self.user)
        self.url = reverse('accounts:account')

    def profile(self, **overrides):
        return {'action': 'profile', 'username': 'owner', 'email': 'owner@example.com', 'first_name': 'Matheus', 'last_name': 'Lisboa', **overrides}

    def test_view_and_private_access(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Minha conta')
        self.assertContains(response, 'owner@example.com')
        self.assertNotContains(response, 'other@example.com')
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), reverse('accounts:login')+'?next='+self.url)

    def test_profile_only_edits_self_and_not_permissions(self):
        response = self.client.post(self.url, self.profile(id=self.other.pk, system_role='SYSADMIN', is_staff='true', is_superuser='true'))
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Matheus')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.system_role, 'MEMBER')
        self.assertEqual(self.other.first_name, '')

    def test_identity_changes_require_password_and_validate_duplicates(self):
        response = self.client.post(self.url, self.profile(email='new@example.com'))
        self.assertContains(response, 'Informe sua senha atual')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'owner@example.com')
        response = self.client.post(self.url, self.profile(email='OTHER@example.com', current_password='Old-password-8294!'))
        self.assertContains(response, 'Este e-mail já está em uso.')
        response = self.client.post(self.url, self.profile(username='other', current_password='Old-password-8294!'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(self.url, self.profile(email='NEW@example.com', username='new-owner', current_password='Old-password-8294!'))
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertEqual(self.user.username, 'new-owner')

    def test_preferences_persist_and_do_not_grant_roles(self):
        response = self.client.post(self.url, {'action':'preferences', 'theme_preference':'dark','onboarding_role':'MANAGER','education_level':'UNDERGRADUATE','app_goal':'ORGANIZE_STUDIES','app_goal_details':'Rotina semanal','system_role':'SYSADMIN'})
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme_preference,'dark')
        self.assertEqual(self.user.system_role,'MEMBER')
        self.assertContains(self.client.get(self.url), 'data-theme-preference="dark"')
        self.assertTrue(self.user.has_completed_onboarding)

    def test_preferences_reject_invalid_values(self):
        response = self.client.post(self.url, {'action':'preferences','theme_preference':'evil','app_goal':'OTHER','app_goal_details':''})
        self.assertEqual(response.status_code,200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme_preference,'system')

    def test_password_change_keeps_current_session_and_revokes_others(self):
        other_session = Client(); other_session.force_login(self.user)
        response = self.client.post(self.url, {'action':'password','old_password':'wrong','new_password1':'New-password-7201!','new_password2':'New-password-7201!'})
        self.assertEqual(response.status_code,200)
        response = self.client.post(self.url, {'action':'password','old_password':'Old-password-8294!','new_password1':'New-password-7201!','new_password2':'New-password-7201!'})
        self.assertRedirects(response,self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-password-7201!'))
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(other_session.get(self.url).status_code,302)

    def test_theme_endpoint_validation_auth_and_csrf(self):
        url=reverse('accounts:update-theme')
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertEqual(self.client.post(url,{'theme':'invalid'}).status_code,400)
        self.assertEqual(self.client.post(url,{'theme':'light'}).status_code,200)
        self.user.refresh_from_db(); self.assertEqual(self.user.theme_preference,'light')
        strict=Client(enforce_csrf_checks=True); strict.force_login(self.user)
        self.assertEqual(strict.post(url,{'theme':'dark'}).status_code,403)
        self.assertEqual(strict.post(self.url,self.profile()).status_code,403)
        self.client.logout(); self.assertEqual(self.client.post(url,{'theme':'dark'}).status_code,302)

    def test_invalid_action_does_not_update(self):
        self.assertEqual(self.client.post(self.url,self.profile(action='admin')).status_code,400)
        self.user.refresh_from_db(); self.assertEqual(self.user.first_name,'')
