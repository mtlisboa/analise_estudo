from datetime import datetime, timezone as dt_timezone

from django.test import TestCase
from django.urls import reverse

from features.accounts.models import User
from features.analytics_dashboard.services import build_dashboard
from features.users_manager.models import (
    Classroom, ClassroomMembership, ClassroomTest, MembershipStatus,
    Organization, OrganizationMembership, SelfAssessment,
)


class AnalyticsScopeRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="manager")
        cls.teacher = User.objects.create_user(username="teacher")
        cls.student = User.objects.create_user(username="student")
        cls.other = User.objects.create_user(username="other")
        cls.org = Organization.objects.create(name="School", owner=cls.owner)
        for user, teacher in [(cls.owner, True), (cls.teacher, True), (cls.student, False), (cls.other, False)]:
            OrganizationMembership.objects.create(organization=cls.org, user=user,
                is_teacher=teacher, is_student=not teacher, added_by=cls.owner)
        cls.room = Classroom.objects.create(name="Assigned", organization=cls.org, owner=cls.teacher)
        cls.other_room = Classroom.objects.create(name="Unassigned", organization=cls.org, owner=cls.owner)
        for room, user, role in [(cls.room, cls.teacher, 'TEACHER'), (cls.room, cls.student, 'STUDENT'),
                                 (cls.other_room, cls.other, 'STUDENT')]:
            ClassroomMembership.objects.create(classroom=room, user=user, role=role,
                status=MembershipStatus.ACTIVE, invited_by=cls.owner)
        for user in (cls.student, cls.other):
            SelfAssessment.objects.create(user=user, focus=4, organization=3, comprehension=5, motivation=4)

    def test_teacher_cannot_see_other_classroom_or_student(self):
        data = build_dashboard(self.teacher, {})
        self.assertEqual([r.pk for r in data['classrooms']], [self.room.pk])
        self.assertEqual([u.pk for u in data['students']], [self.student.pk])
        self.assertEqual(data['analytics_payload']['scatter2d']['names'], ['student'])

    def test_manipulated_filter_does_not_expand_teacher_scope(self):
        data = build_dashboard(self.teacher, {'classroom': str(self.other_room.pk), 'student': str(self.other.pk)})
        self.assertEqual(data['analytics_payload']['scatter2d']['names'], ['student'])
        self.assertIsNone(data['filters']['classroom'])

    def test_owner_sees_all_classrooms_without_teacher_membership(self):
        OrganizationMembership.objects.filter(user=self.owner).delete()
        data = build_dashboard(self.owner, {})
        self.assertEqual(data['metrics']['classrooms'], 2)
        self.assertEqual(data['metrics']['students'], 2)

    def test_student_does_not_count_draft_tests(self):
        ClassroomTest.objects.create(classroom=self.room, title="Draft", created_by=self.teacher, is_published=False)
        self.assertEqual(build_dashboard(self.student, {})['metrics']['tests'], 0)
        self.assertEqual(build_dashboard(self.teacher, {})['metrics']['tests'], 1)

    def test_revoked_teacher_role_removes_group_access(self):
        OrganizationMembership.objects.filter(user=self.teacher).update(is_teacher=False, is_student=True)
        data = build_dashboard(self.teacher, {})
        self.assertEqual(data['metrics']['classrooms'], 0)
        self.assertNotIn(self.student.pk, [u.pk for u in data['students']])

    def test_removed_organization_member_cannot_see_classroom(self):
        OrganizationMembership.objects.filter(user=self.student).delete()
        self.client.force_login(self.student)
        response = self.client.get(reverse('users-manager:classroom-detail', args=[self.room.pk]))
        self.assertEqual(response.status_code, 403)

    def test_inactive_organization_blocks_classroom_actions(self):
        self.org.is_active = False
        self.org.save()
        self.client.force_login(self.teacher)
        for route in ['classroom-detail', 'classroom-invite', 'classroom-test-create']:
            self.assertEqual(self.client.get(reverse('users-manager:' + route, args=[self.room.pk])).status_code, 404)

    def test_day_grouping_uses_local_timezone(self):
        SelfAssessment.objects.filter(user=self.student).update(created_at=datetime(2026, 1, 2, 1, 0, tzinfo=dt_timezone.utc))
        data = build_dashboard(self.student, {'period': 'all'})
        self.assertEqual(data['analytics_payload']['timeline']['dates'], ['2026-01-01'])

    def test_role_counts_deduplicate_students_across_organizations(self):
        other_org = Organization.objects.create(name="Second", owner=self.owner)
        OrganizationMembership.objects.create(organization=other_org, user=self.student, is_student=True, added_by=self.owner)
        data = build_dashboard(self.owner, {})
        self.assertEqual(data['analytics_payload']['roles']['values'][0], 2)

    def test_independent_user_can_analyze_own_self_assessments(self):
        user = User.objects.create_user(username="independent")
        SelfAssessment.objects.create(user=user, focus=5, organization=5, comprehension=5, motivation=5)
        data = build_dashboard(user, {})
        self.assertEqual(data['metrics']['assessment_average'], 100)
        self.assertEqual(data['analytics_payload']['scatter2d']['names'], ['independent'])

    def test_teacher_role_in_another_organization_does_not_restore_revoked_role(self):
        OrganizationMembership.objects.filter(user=self.teacher).update(is_teacher=False, is_student=True)
        other_org = Organization.objects.create(name="Other school", owner=self.other)
        OrganizationMembership.objects.create(organization=other_org, user=self.teacher,
            is_teacher=True, added_by=self.other)
        data = build_dashboard(self.teacher, {"organization": str(self.org.pk)})
        self.assertEqual(data["metrics"]["classrooms"], 0)
        self.assertNotIn(self.student.pk, [u.pk for u in data["students"]])
