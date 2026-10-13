from django.test import TestCase
from django.urls import reverse


class DedicatedClassroomsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_institutional_contexts import InstitutionalContextTests
        InstitutionalContextTests.setUpTestData.__func__(cls)

    def test_list_is_scoped_and_educational_roles_only_see_enrolments(self):
        url = reverse('institutions:classrooms')
        for role in ('ADMIN','MANAGER','OPERATOR','TEACHER','STUDENT'):
            self.client.force_login(self.users[role])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Turma própria')
            self.assertNotContains(response, 'Turma externa')
            self.assertNotContains(response, reverse('users-manager:classroom-group-detail', args=[self.classroom.group_id]))
            if role in ('TEACHER','STUDENT'):
                self.assertNotContains(response, 'Turma sem vínculo')
            self.assertContains(response, reverse('institutions:classroom', args=[self.classroom.pk]))

    def test_read_only_management_enters_room_without_write_access(self):
        for role in ('MANAGER','OPERATOR'):
            self.client.force_login(self.users[role])
            response = self.client.get(reverse('institutions:classroom', args=[self.classroom.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, reverse('institutions:classrooms'))
            self.assertNotContains(response, 'Editar imagem da sala')
            self.assertEqual(self.client.post(reverse('users-manager:classroom-notice-create', args=[self.classroom.pk]),
                {'title':'Bloqueado','body':'texto'}).status_code, 403)

    def test_old_tree_entry_redirects_to_dedicated_area(self):
        self.client.force_login(self.admin)
        for url in [reverse('users-manager:dashboard'), reverse('users-manager:organization-detail', args=[self.organization.pk]),
                    reverse('users-manager:classroom-group-detail', args=[self.classroom.group_id])]:
            self.assertRedirects(self.client.get(url), reverse('institutions:classrooms'))
        self.assertEqual(self.client.get(reverse('users-manager:organization-detail', args=[self.other.pk])).status_code,403)
        self.assertRedirects(self.client.get(reverse('users-manager:classroom-detail', args=[self.classroom.pk])),
                             reverse('institutions:classroom', args=[self.classroom.pk]))

    def test_guardian_and_unenrolled_student_cannot_enter_room(self):
        self.client.force_login(self.users['GUARDIAN'])
        self.assertEqual(self.client.get(reverse('institutions:classrooms')).status_code,403)
        self.client.force_login(self.users['STUDENT'])
        self.assertEqual(self.client.get(reverse('institutions:classroom', args=[self.other_classroom.pk])).status_code,403)
