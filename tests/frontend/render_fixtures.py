"""Render real templates against a disposable in-memory database for DOM tests."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.development"
os.environ["SQLITE_PATH"] = ":memory:"
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver"

import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from features.accounts.models import User
from features.assessments.models import Assessment, AssessmentType

call_command("migrate", verbosity=0)
user = User.objects.create_user(username="frontend-test", onboarding_completed_at=timezone.now())
kind = AssessmentType.objects.first()
assessment = Assessment.objects.create(owner=user, subject="Original subject", topic="Original topic",
    technique=kind.default_technique, observations=["Original observation"])
assessment.assessment_types.add(kind)
client = Client()
client.force_login(user)
invalid = client.post(reverse("assessments:update", args=[assessment.pk]), {
    "subject": "Old failed edit", "topic": "", "assessment_types": [kind.pk],
    "observations": "Previous edit observation", "technique": kind.default_technique_id,
})
from features.users_manager.models import Organization, OrganizationMembership, Classroom, ClassroomMembership
org = Organization.objects.create(name="Frontend school", owner=user)
teacher = User.objects.create_user(username="teacher-fixture")
student = User.objects.create_user(username="student-fixture")
for member, is_teacher in [(teacher, True), (student, False)]:
    OrganizationMembership.objects.create(organization=org, user=member,
        is_teacher=is_teacher, is_student=not is_teacher, added_by=user)
room = Classroom.objects.create(name="Fixture room", organization=org, owner=teacher)
ClassroomMembership.objects.create(classroom=room, user=student, role="STUDENT", status="ACTIVE", invited_by=teacher)
from datetime import timedelta
from features.users_manager.models import SelfAssessment, ClassroomTest
for index, name in enumerate(["Ana Lima", "Bruno Santos", "Clara Mendes", "Diego Alves"]):
    pupil = User.objects.create_user(username="visual-student-" + str(index), first_name=name)
    OrganizationMembership.objects.create(organization=org, user=pupil, is_student=True, added_by=user)
    ClassroomMembership.objects.create(classroom=room, user=pupil, role="STUDENT", status="ACTIVE", invited_by=teacher)
    for day in range(6):
        SelfAssessment.objects.create(user=pupil, focus=2 + (index + day) % 4,
            organization=3 + index % 3, comprehension=2 + day % 4, motivation=3 + (day + index) % 3,
            created_at=timezone.now() - timedelta(days=5-day))
ClassroomTest.objects.create(classroom=room, title="Revisão de conceitos", created_by=teacher)
print(json.dumps({
    "analytics_overview": client.get(reverse("analytics-dashboard:dashboard")).content.decode(),
    "analytics": client.get(reverse("analytics-dashboard:dashboard"), {
        "organization": org.pk, "teacher": teacher.pk, "classroom": room.pk, "student": student.pk,
    }).content.decode(),
    "assessment": invalid.content.decode(),
    "chat": client.get(reverse("ia-integrations:chat-bot")).content.decode(),
}))
