from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.accounts.models import User
from features.users_manager.models import ClassroomGroup, Classroom, ClassroomMembership, Organization, OrganizationMembership, SelfAssessment, EducationalRelationship


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href', '').startswith('/'):
            self.links.append(attrs['href'])


class NavigationRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='owner', onboarding_completed_at=timezone.now())
        cls.student = User.objects.create_user(username='student', onboarding_completed_at=timezone.now())
        cls.org = Organization.objects.create(name='School', owner=cls.owner)
        for user, teacher in [(cls.owner, True), (cls.student, False)]:
            OrganizationMembership.objects.create(organization=cls.org, user=user,
                is_teacher=teacher, is_student=not teacher, added_by=cls.owner)
        cls.group = ClassroomGroup.objects.create(name="Group", organization=cls.org, created_by=cls.owner)
        cls.room = Classroom.objects.create(name='Enrolled', organization=cls.org, group=cls.group, owner=cls.owner)
        cls.other = Classroom.objects.create(name='Not enrolled', organization=cls.org, group=cls.group, owner=cls.owner)
        ClassroomMembership.objects.create(classroom=cls.room, user=cls.student,
            role='STUDENT', status='ACTIVE', invited_by=cls.owner)

    def test_organization_only_links_accessible_classrooms(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('users-manager:classroom-group-detail', args=[self.group.pk]))
        self.assertContains(response, reverse('users-manager:classroom-detail', args=[self.room.pk]))
        self.assertNotContains(response, reverse('users-manager:classroom-detail', args=[self.other.pk]))

    def test_owner_can_follow_all_organization_classroom_links(self):
        # Organizational ownership grants read access even without teaching the class.
        OrganizationMembership.objects.filter(user=self.owner).update(is_teacher=False, is_student=True)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('users-manager:classroom-detail', args=[self.room.pk])).status_code, 200)

    def test_main_navigation_links_resolve_for_each_role(self):
        for user in [self.owner, self.student]:
            self.client.force_login(user)
            for name, args in [('accounts:dashboard', []), ('users-manager:dashboard', []),
                               ('users-manager:organization-detail', [self.org.pk]),
                               ('users-manager:classroom-detail', [self.room.pk]),
                               ('assessments:index', []), ('analytics-dashboard:dashboard', [])]:
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)
                parser = Links(); parser.feed(response.content.decode())
                for href in set(parser.links):
                    with self.subTest(user=user.username, page=name, href=href):
                        linked = self.client.get(href, follow=True)
                        self.assertEqual(linked.status_code, 200)

    def test_nested_forms_return_to_parent(self):
        self.client.force_login(self.owner)
        for route, pk, parent in [
            ('organization-member-add', self.org.pk, reverse('users-manager:organization-detail', args=[self.org.pk])),
            ('classroom-create', self.org.pk, reverse('users-manager:organization-detail', args=[self.org.pk])),
            ('classroom-invite', self.room.pk, reverse('users-manager:classroom-detail', args=[self.room.pk])),
            ('classroom-test-create', self.room.pk, reverse('users-manager:classroom-detail', args=[self.room.pk])),
        ]:
            response = self.client.get(reverse('users-manager:' + route, args=[pk]))
            self.assertContains(response, f'class="back-link" href="{parent}"')

    def test_legacy_relationship_links_redirect_without_mutation(self):
        self.client.force_login(self.owner)
        for method in [self.client.get, self.client.post]:
            response = method(reverse('users-manager:relationship-create'), {'email': 'student@example.com', 'position': 'TEACHER'})
            self.assertRedirects(response, reverse('users-manager:dashboard'))
        self.assertFalse(EducationalRelationship.objects.exists())

    def test_personal_dashboard_has_real_metrics_and_working_diagnostic_link(self):
        SelfAssessment.objects.create(user=self.student, focus=1, organization=2, comprehension=3, motivation=4)
        self.client.force_login(self.student)
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.context['latest_assessment'].score, 50)
        self.assertEqual(response.context['self_assessment_count'], 1)
        self.assertEqual(response.context['assessment_count'], 0)
        self.assertContains(response, reverse('ia-integrations:chat-bot') + '?mode=diagnostic')
        self.assertNotContains(response, '78%')
        self.assertNotContains(response, 'cresceu 23%')

    def test_published_test_instructions_are_visible_to_student(self):
        from features.users_manager.models import ClassroomTest
        ClassroomTest.objects.create(classroom=self.room, title="Activity", created_by=self.owner,
            instructions="Read chapter one.\nAnswer the questions.", is_published=True)
        ClassroomTest.objects.create(classroom=self.room, title="Draft", created_by=self.owner,
            instructions="PRIVATE INSTRUCTIONS", is_published=False)
        self.client.force_login(self.student)
        response = self.client.get(reverse("users-manager:classroom-detail", args=[self.room.pk]))
        self.assertContains(response, "Read chapter one.")
        self.assertContains(response, "Answer the questions.")
        self.assertNotContains(response, "PRIVATE INSTRUCTIONS")
