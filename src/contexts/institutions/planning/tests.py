from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from features.users_manager.models import ClassroomMembership, InstitutionalAccount, Organization, School
from .forms import LessonForm, RequirementForm, StudentForm, TeacherForm
from .models import Lesson, Offer, Period, Requirement, Slot, Student, Teacher
from .services import authorize, distribute, generate_timetable, import_students, mutate, pending_issues, publish, validate_existing


class PlanningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(username="planning-admin", onboarding_completed_at=timezone.now())
        cls.organization = Organization.objects.create(name="Escola", owner=cls.admin)
        School.objects.create(organization=cls.organization, legal_name="Escola", display_name="Escola",
            school_type="PRIVATE", email_domain="planning.edu.br", address="Rua", city="João Pessoa",
            state="PB", approved_by=cls.admin)
        cls.accounts = {}
        for role in ("ADMIN", "OPERATOR", "TEACHER", "STUDENT", "MANAGER", "GUARDIAN"):
            user = cls.admin if role == "ADMIN" else User.objects.create_user(
                username="planning-" + role.lower(), onboarding_completed_at=timezone.now())
            cls.accounts[role] = InstitutionalAccount.objects.create(
                user=user, organization=cls.organization, registration=role.lower(),
                email=role.lower() + "@planning.edu.br", role=role, created_by=cls.admin)
        cls.period = Period.objects.create(organization=cls.organization, name="2026",
            starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31))
        cls.offer = Offer.objects.create(period=cls.period, name="7 A", grade="7", shift="MORNING", capacity=2)
        cls.offer_b = Offer.objects.create(period=cls.period, name="7 B", grade="7", shift="MORNING", capacity=2)
        cls.slot = Slot.objects.create(period=cls.period, weekday=1, starts_at=time(8), ends_at=time(9), shift="MORNING")
        cls.slot2 = Slot.objects.create(period=cls.period, weekday=1, starts_at=time(9), ends_at=time(10), shift="MORNING")
        cls.teacher = Teacher.objects.create(period=cls.period, account=cls.accounts["TEACHER"],
            subjects="MATEMÁTICA", max_lessons=2)
        cls.teacher.availability.add(cls.slot, cls.slot2)

    def student(self, registration, **kwargs):
        data = dict(period=self.period, registration=registration, name=registration,
                    grade="7", shift="MORNING")
        data.update(kwargs)
        return Student.objects.create(**data)

    def requirement(self, offer=None, **kwargs):
        data = dict(offer=offer or self.offer, subject="MATEMÁTICA", weekly_lessons=1)
        data.update(kwargs)
        return Requirement.objects.create(**data)

    def operation(self, callback, actor=None):
        self.period.refresh_from_db()
        return mutate(actor or self.admin, self.period.pk, self.period.revision, callback)

    def test_access_roles_and_scoped_routes(self):
        for role, account in self.accounts.items():
            self.client.force_login(account.user)
            status = 200 if role in ("ADMIN", "OPERATOR") else 403
            self.assertEqual(self.client.get(reverse("planning:index")).status_code, status)
            self.assertEqual(self.client.get(reverse("planning:detail", args=[self.period.pk])).status_code, status)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("planning:index")).status_code, 302)

    def test_other_institution_and_disabled_organization_denied(self):
        other = Organization.objects.create(name="Other", owner=self.admin)
        foreign = Period.objects.create(organization=other, name="Other", starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31))
        self.client.force_login(self.accounts["OPERATOR"].user)
        self.assertEqual(self.client.get(reverse("planning:detail", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("planning:action", args=[foreign.pk, "distribute"]),
            {"revision": 0}).status_code, 404)
        self.organization.is_active = False
        self.organization.save()
        with self.assertRaises(PermissionDenied):
            authorize(self.admin)

    def test_roster_import_is_atomic_and_normalizes(self):
        self.operation(lambda p: import_students(p, "abc;Ana;7;MORNING;2025 A\nbcd;Bruno;7;MORNING;2025 A"))
        self.assertEqual(self.period.students.count(), 2)
        with self.assertRaises(ValidationError):
            self.operation(lambda p: import_students(p, "new;Nova;7;MORNING\ninvalid line"))
        self.assertFalse(self.period.students.filter(registration="new").exists())

    def test_import_duplicate_does_not_overwrite(self):
        self.student("abc")
        with self.assertRaises(ValidationError):
            self.operation(lambda p: import_students(p, "abc;Outro nome;7;MORNING"))
        self.assertEqual(self.period.students.get(registration="abc").name, "abc")

    def test_same_cohort_prefers_same_offer_with_capacity(self):
        a = self.student("a", previous_cohort="2025 / A")
        b = self.student("b", previous_cohort="2025 / A")
        c = self.student("c", previous_cohort="2025 / B")
        self.operation(distribute)
        a.refresh_from_db()
        b.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual(a.offer_id, b.offer_id)
        self.assertNotEqual(a.offer_id, c.offer_id)
        self.assertLessEqual(self.offer.students.count(), 2)

    def test_distribution_preserves_locked_and_reports_no_vacancies(self):
        locked = self.student("a", offer=self.offer_b, locked=True)
        afternoon = self.student("b", shift="AFTERNOON")
        issues = self.operation(distribute)
        locked.refresh_from_db()
        afternoon.refresh_from_db()
        self.assertEqual(locked.offer_id, self.offer_b.pk)
        self.assertIsNone(afternoon.offer_id)
        self.assertEqual(len(issues), 1)

    def test_distribution_is_deterministic_and_splits_large_groups(self):
        for number in range(5):
            self.student(f"s{number}", previous_cohort="same")
        self.assertEqual(len(self.operation(distribute)), 1)
        first = list(self.period.students.order_by("registration").values_list("offer_id", flat=True))
        self.operation(distribute)
        self.assertEqual(first, list(self.period.students.order_by("registration").values_list("offer_id", flat=True)))

    def test_published_history_is_used_not_unpublished_roster(self):
        past = Period.objects.create(organization=self.organization, name="2025",
            starts_on=date(2025, 1, 1), ends_on=date(2025, 12, 31), published_at=timezone.now())
        Offer.objects.create(period=past, name="6 A", grade="6", shift="MORNING",
            capacity=30, published_roster=["a", "z"])
        a = self.student("a")
        self.student("b")
        z = self.student("z")
        self.operation(distribute)
        a.refresh_from_db()
        z.refresh_from_db()
        self.assertEqual(a.offer_id, z.offer_id)

    def test_manual_transfer_rejects_full_or_wrong_shift(self):
        self.student("a", offer=self.offer)
        self.student("b", offer=self.offer)
        student = self.student("c")
        student.offer = self.offer
        with self.assertRaises(ValidationError):
            student.full_clean()
        student.offer, student.shift = self.offer_b, "EVENING"
        with self.assertRaises(ValidationError):
            student.full_clean()

    def test_scheduler_assigns_teacher_and_avoids_double_booking(self):
        first = self.requirement()
        second = self.requirement(self.offer_b)
        self.assertEqual(self.operation(generate_timetable), [])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.teacher_id, self.teacher.pk)
        self.assertEqual(second.teacher_id, self.teacher.pk)
        self.assertNotEqual(first.lessons.get().slot_id, second.lessons.get().slot_id)
        validate_existing(self.period)

    def test_scheduler_respects_capacity_and_reports_incomplete(self):
        req = self.requirement(weekly_lessons=3)
        issues = self.operation(generate_timetable)
        self.assertEqual(req.lessons.count(), 2)
        self.assertEqual(len(issues), 1)

    def test_scheduler_needs_explicit_availability(self):
        self.teacher.availability.clear()
        req = self.requirement()
        self.assertTrue(self.operation(generate_timetable))
        self.assertFalse(req.lessons.exists())

    def test_scheduler_cannot_use_unqualified_teacher(self):
        req = self.requirement(subject="HISTÓRIA")
        self.assertTrue(self.operation(generate_timetable))
        req.refresh_from_db()
        self.assertIsNone(req.teacher_id)
        self.assertFalse(req.lessons.exists())

    def test_fixed_lesson_survives_regeneration(self):
        req = self.requirement(teacher=self.teacher)
        lesson = Lesson.objects.create(requirement=req, slot=self.slot2, locked=True)
        self.assertEqual(self.operation(generate_timetable), [])
        self.assertTrue(Lesson.objects.filter(pk=lesson.pk, slot=self.slot2).exists())
        req.refresh_from_db()
        self.assertEqual(req.teacher_id, self.teacher.pk)

    def test_overlap_detected_even_with_different_slot_ids(self):
        req = self.requirement(teacher=self.teacher)
        Lesson.objects.create(requirement=req, slot=self.slot)
        other_slot = Slot.objects.create(period=self.period, weekday=1, starts_at=time(8, 30),
            ends_at=time(9, 30), shift="MORNING")
        self.teacher.availability.add(other_slot)
        other_req = self.requirement(self.offer_b, teacher=self.teacher)
        with self.assertRaises(ValidationError):
            Lesson(requirement=other_req, slot=other_slot).full_clean()

    def test_teacher_conflicts_across_overlapping_periods(self):
        req = self.requirement(teacher=self.teacher)
        Lesson.objects.create(requirement=req, slot=self.slot)
        other = Period.objects.create(organization=self.organization, name="Concurrent",
            starts_on=date(2026, 2, 1), ends_on=date(2026, 3, 1))
        offer = Offer.objects.create(period=other, name="Other", grade="7", shift="MORNING", capacity=20)
        teacher = Teacher.objects.create(period=other, account=self.accounts["TEACHER"],
            subjects="MATEMÁTICA", max_lessons=2)
        slot = Slot.objects.create(period=other, weekday=1, starts_at=time(8), ends_at=time(9), shift="MORNING")
        teacher.availability.add(slot)
        req2 = Requirement.objects.create(offer=offer, subject="MATEMÁTICA", weekly_lessons=1, teacher=teacher)
        with self.assertRaises(ValidationError):
            Lesson(requirement=req2, slot=slot).full_clean()

    def test_stale_revision_does_not_mutate(self):
        self.operation(lambda p: import_students(p, "abc;Ana;7;MORNING"))
        with self.assertRaises(ValidationError):
            mutate(self.admin, self.period.pk, 0, lambda p: import_students(p, "def;Bia;7;MORNING"))
        self.assertFalse(self.period.students.filter(registration="def").exists())

    def test_publish_is_idempotent_and_syncs_memberships(self):
        self.student("student", offer=self.offer)
        self.requirement()
        self.requirement(self.offer_b)
        self.operation(generate_timetable)
        code = self.offer.code
        self.assertEqual(self.operation(lambda p: publish(p, self.admin)), 0)
        self.offer.refresh_from_db()
        classroom_id = self.offer.classroom_id
        membership = ClassroomMembership.objects.get(classroom_id=classroom_id, user=self.accounts["STUDENT"].user)
        self.assertEqual(membership.status, "ACTIVE")
        self.operation(lambda p: publish(p, self.admin))
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.code, code)
        self.assertEqual(self.offer.classroom_id, classroom_id)
        self.assertEqual(self.offer.published_roster, ["student"])
        self.assertEqual(len(self.offer.published_schedule), 1)
        self.period.refresh_from_db()
        self.assertEqual(self.period.published_revision, self.period.revision)

    def test_publish_blocks_incomplete_roster(self):
        self.student("student")
        with self.assertRaises(ValidationError):
            self.operation(lambda p: publish(p, self.admin))
        self.offer.refresh_from_db()
        self.assertIsNone(self.offer.classroom_id)

    def test_draft_move_only_changes_published_memberships_on_publish(self):
        student = self.student("student", offer=self.offer)
        self.requirement()
        self.requirement(self.offer_b)
        self.operation(generate_timetable)
        self.operation(lambda p: publish(p, self.admin))
        self.offer.refresh_from_db()
        original = self.offer.classroom_id
        student.offer = self.offer_b
        student.save()
        self.assertEqual(ClassroomMembership.objects.get(classroom_id=original,
            user=self.accounts["STUDENT"].user).status, "ACTIVE")
        self.operation(lambda p: publish(p, self.admin))
        self.assertEqual(ClassroomMembership.objects.get(classroom_id=original,
            user=self.accounts["STUDENT"].user).status, "REMOVED")

    def test_manual_forms_reject_cross_period_references_and_missing_values(self):
        other = Period.objects.create(organization=self.organization, name="Other",
            starts_on=date(2027, 1, 1), ends_on=date(2027, 12, 31))
        foreign = Offer.objects.create(period=other, name="Other", grade="7", shift="MORNING", capacity=20)
        form = StudentForm({"revision": 0, "registration": "abc", "name": "Ana", "grade": "7",
            "shift": "MORNING", "offer": foreign.pk}, period=self.period)
        self.assertFalse(form.is_valid())
        for cls in (RequirementForm, LessonForm, TeacherForm):
            self.assertFalse(cls({"revision": 0}, period=self.period).is_valid())

    def test_operator_can_create_student_without_provisioning_identity(self):
        self.client.force_login(self.accounts["OPERATOR"].user)
        response = self.client.post(reverse("planning:create", args=[self.period.pk, "student"]),
            {"revision": 0, "registration": "new", "name": "Novo aluno", "grade": "7", "shift": "MORNING"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.period.students.filter(registration="new").exists())
        self.assertFalse(InstitutionalAccount.objects.filter(registration="new").exists())

    def test_invalid_revision_renders_error_without_mutation(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("planning:create", args=[self.period.pk, "offer"]),
            {"name": "X", "grade": "7", "shift": "MORNING", "capacity": 20})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.period.offers.filter(name="X").exists())

    def test_get_cannot_trigger_generation(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("planning:action", args=[self.period.pk, "schedule"])).status_code, 405)

    def test_csrf_required_and_shared_components_preserved(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("planning:action", args=[self.period.pk, "distribute"]),
            {"revision": 0}).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("planning:detail", args=[self.period.pk]))
        self.assertTemplateUsed(response, "components/layout/sidebar.html")
        self.assertTemplateUsed(response, "notifications/bell.html")

    def test_published_itinerary_visible_only_to_assigned_teacher(self):
        self.requirement()
        self.requirement(self.offer_b)
        self.operation(generate_timetable)
        self.operation(lambda p: publish(p, self.admin))
        self.client.force_login(self.accounts["TEACHER"].user)
        response = self.client.get(reverse("institutions:professor"))
        self.assertContains(response, "Horários publicados")
        self.assertContains(response, "MATEMÁTICA")
