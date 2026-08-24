from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.assessments.models import Assessment, AssessmentTechnique, AssessmentType

User = get_user_model()


class AssessmentManagerTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="matheus",
            email="matheus@example.com",
            password="senha-forte-123",
        )
        self.other_user = User.objects.create_user(
            username="outra-pessoa",
            email="outra@example.com",
            password="senha-forte-456",
        )
        self.client.force_login(self.user)
        self.memorization = AssessmentType.objects.get(code="memorization")
        self.deduction = AssessmentType.objects.get(code="deduction")

    def assessment_data(self, **overrides):
        data = {
            "subject": "Matemática",
            "topic": "Funções quadráticas",
            "observations": "Sem consulta\nLimite de 30 minutos",
            "assessment_types": [self.memorization.pk, self.deduction.pk],
            "technique": "",
        }
        data.update(overrides)
        return data

    def create_assessment(self, owner=None, **overrides):
        assessment = Assessment.objects.create(
            owner=owner or self.user,
            subject=overrides.get("subject", "Matemática"),
            topic=overrides.get("topic", "Funções quadráticas"),
            observations=overrides.get("observations", ["Sem consulta"]),
            technique=self.memorization.default_technique,
            technique_selected_automatically=True,
        )
        assessment.assessment_types.add(self.memorization)
        return assessment

    def test_module_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("assessments:index"))
        self.assertRedirects(
            response,
            f'{reverse("accounts:login")}?next={reverse("assessments:index")}',
        )

    def test_user_creates_assessment_with_default_technique(self):
        response = self.client.post(reverse("assessments:create"), self.assessment_data())

        assessment = Assessment.objects.get(owner=self.user)
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(assessment.observations, ["Sem consulta", "Limite de 30 minutos"])
        self.assertSetEqual(
            set(assessment.assessment_types.all()),
            {self.memorization, self.deduction},
        )
        self.assertEqual(assessment.technique, self.memorization.default_technique)
        self.assertTrue(assessment.technique_selected_automatically)

    def test_user_can_override_default_technique(self):
        chosen_technique = AssessmentTechnique.objects.get(code="scenario-application")
        response = self.client.post(
            reverse("assessments:create"),
            self.assessment_data(technique=chosen_technique.pk),
        )

        assessment = Assessment.objects.get(owner=self.user)
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(assessment.technique, chosen_technique)
        self.assertFalse(assessment.technique_selected_automatically)

    def test_user_can_edit_own_assessment(self):
        assessment = self.create_assessment()
        technique = AssessmentTechnique.objects.get(code="problem-solving")
        response = self.client.post(
            reverse("assessments:update", kwargs={"pk": assessment.pk}),
            self.assessment_data(
                subject="Física",
                topic="Cinemática",
                observations="Usar unidades do SI",
                assessment_types=[self.deduction.pk],
                technique=technique.pk,
            ),
        )

        assessment.refresh_from_db()
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(assessment.subject, "Física")
        self.assertEqual(assessment.observations, ["Usar unidades do SI"])
        self.assertEqual(assessment.technique, technique)

    def test_user_cannot_edit_another_users_assessment(self):
        assessment = self.create_assessment(owner=self.other_user)
        response = self.client.post(
            reverse("assessments:update", kwargs={"pk": assessment.pk}),
            self.assessment_data(),
        )
        self.assertEqual(response.status_code, 404)

    def test_list_and_search_only_show_owned_assessments(self):
        self.create_assessment(topic="Álgebra linear")
        self.create_assessment(owner=self.other_user, topic="Geometria")

        response = self.client.get(reverse("assessments:index"), {"q": "Álgebra"})

        self.assertContains(response, "Álgebra linear")
        self.assertNotContains(response, "Geometria")

    def test_at_least_one_assessment_type_is_required(self):
        response = self.client.post(
            reverse("assessments:create"),
            self.assessment_data(assessment_types=[]),
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Este campo é obrigatório", status_code=422)
        self.assertFalse(Assessment.objects.exists())
