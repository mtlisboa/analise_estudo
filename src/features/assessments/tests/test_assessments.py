from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from features.assessments.models import (
    Assessment,
    AssessmentTechnique,
    AssessmentType,
    Question,
    QuestionBankItem,
)

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

    def test_user_can_add_multiple_choice_question_to_own_assessment(self):
        assessment = self.create_assessment()

        response = self.client.post(
            reverse("assessments:question-create", kwargs={"assessment_pk": assessment.pk}),
            {
                "question_type": Question.Type.MULTIPLE_CHOICE,
                "statement": "Qual é a raiz positiva de x² = 9?",
                "options": "1\n3\n6\n9",
                "correct_answer": "3",
                "explanation": "Três ao quadrado é igual a nove.",
                "points": "2.5",
            },
        )

        question = Question.objects.get(assessment=assessment)
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(question.options, ["1", "3", "6", "9"])
        self.assertEqual(question.correct_answer, "3")
        self.assertEqual(question.order, 1)

    def test_user_can_add_open_ended_question(self):
        assessment = self.create_assessment()

        response = self.client.post(
            reverse("assessments:question-create", kwargs={"assessment_pk": assessment.pk}),
            {
                "question_type": Question.Type.OPEN_ENDED,
                "statement": "Explique como a parábola se comporta.",
                "options": "Esta alternativa deve ser descartada",
                "correct_answer": "A resposta deve mencionar concavidade e vértice.",
                "explanation": "",
                "points": "3",
            },
        )

        question = Question.objects.get(assessment=assessment)
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(question.options, [])
        self.assertEqual(question.question_type, Question.Type.OPEN_ENDED)

    def test_multiple_choice_question_requires_matching_answer(self):
        assessment = self.create_assessment()

        response = self.client.post(
            reverse("assessments:question-create", kwargs={"assessment_pk": assessment.pk}),
            {
                "question_type": Question.Type.MULTIPLE_CHOICE,
                "statement": "Selecione uma alternativa.",
                "options": "A\nB",
                "correct_answer": "C",
                "points": "1",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertContains(
            response,
            "O gabarito deve ser idêntico a uma das alternativas.",
            status_code=422,
        )
        self.assertFalse(Question.objects.exists())

    def test_user_cannot_add_question_to_another_users_assessment(self):
        assessment = self.create_assessment(owner=self.other_user)

        response = self.client.post(
            reverse("assessments:question-create", kwargs={"assessment_pk": assessment.pk}),
            {
                "question_type": Question.Type.OPEN_ENDED,
                "statement": "Questão indevida",
                "points": "1",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Question.objects.exists())

    def test_index_lists_questions_inside_the_assessment(self):
        assessment = self.create_assessment()
        Question.objects.create(
            assessment=assessment,
            statement="Explique a função do discriminante.",
            question_type=Question.Type.OPEN_ENDED,
            correct_answer="Determinar a quantidade de raízes reais.",
            points=2,
            order=1,
        )

        response = self.client.get(reverse("assessments:index"))

        self.assertContains(response, "Adicionar questão")
        self.assertContains(response, "Explique a função do discriminante.")
        self.assertContains(response, "1 questão criada")

    def bank_question_data(self, **overrides):
        data = {
            "subject": "Matemática",
            "topic": "Funções quadráticas",
            "question_type": Question.Type.MULTIPLE_CHOICE,
            "statement": "Qual é o valor de x em x + 2 = 5?",
            "options": "1\n2\n3\n4",
            "correct_answer": "3",
            "explanation": "Subtraia dois dos dois lados.",
            "default_points": "2",
        }
        data.update(overrides)
        return data

    def create_bank_question(self, **overrides):
        data = self.bank_question_data(**overrides)
        return QuestionBankItem.objects.create(
            owner=self.user,
            subject=data["subject"],
            topic=data["topic"],
            question_type=data["question_type"],
            statement=data["statement"],
            options=data["options"].splitlines() if isinstance(data["options"], str) else data["options"],
            correct_answer=data["correct_answer"],
            explanation=data["explanation"],
            default_points=data["default_points"],
        )

    def test_manual_question_is_saved_in_reusable_bank(self):
        response = self.client.post(
            reverse("assessments:bank-question-create"),
            self.bank_question_data(),
        )

        item = QuestionBankItem.objects.get()
        self.assertRedirects(response, reverse("assessments:question-bank"))
        self.assertEqual(item.creation_method, QuestionBankItem.CreationMethod.MANUAL)

    def test_user_can_derive_and_edit_an_existing_question(self):
        source = self.create_bank_question()
        response = self.client.post(
            reverse("assessments:bank-question-derive", args=(source.pk,)),
            self.bank_question_data(statement="Uma nova versão da questão"),
        )

        derived = QuestionBankItem.objects.exclude(pk=source.pk).get()
        self.assertRedirects(response, reverse("assessments:question-bank"))
        self.assertEqual(derived.source_question, source)
        self.assertEqual(derived.creation_method, QuestionBankItem.CreationMethod.DERIVED)
        self.assertEqual(source.statement, "Qual é o valor de x em x + 2 = 5?")

    @patch("features.assessments.services.request_ai_json")
    def test_ai_can_create_a_completely_new_question(self, ai_json):
        ai_json.return_value = {
            "statement": "Qual gráfico representa uma função quadrática?",
            "question_type": "multiple_choice",
            "options": ["Parábola", "Reta"],
            "correct_answer": "Parábola",
            "explanation": "Funções quadráticas produzem parábolas.",
            "points": 2,
        }

        response = self.client.post(
            reverse("assessments:bank-question-ai-create"),
            {
                "subject": "Matemática",
                "topic": "Funções quadráticas",
                "instructions": "Crie uma questão visual intermediária.",
            },
        )

        item = QuestionBankItem.objects.get()
        self.assertRedirects(response, reverse("assessments:question-bank"))
        self.assertEqual(item.creation_method, QuestionBankItem.CreationMethod.AI_GENERATED)

    @patch("features.assessments.services.request_ai_json")
    def test_ai_edit_preserves_source_and_creates_new_version(self, ai_json):
        source = self.create_bank_question()
        ai_json.return_value = {
            "statement": "Resolva x + 2 = 5 e justifique.",
            "question_type": "open_ended",
            "options": [],
            "correct_answer": "x = 3",
            "explanation": "Subtraia dois.",
            "points": 2,
        }

        response = self.client.post(
            reverse("assessments:bank-question-ai-edit", args=(source.pk,)),
            {"instructions": "Transforme em discursiva e peça justificativa."},
        )

        edited = QuestionBankItem.objects.exclude(pk=source.pk).get()
        self.assertRedirects(response, reverse("assessments:question-bank"))
        self.assertEqual(edited.creation_method, QuestionBankItem.CreationMethod.AI_EDITED)
        self.assertEqual(edited.source_question, source)

    def test_existing_bank_questions_can_be_added_manually_to_assessment(self):
        assessment = self.create_assessment()
        item = self.create_bank_question()

        response = self.client.post(
            reverse("assessments:bank-questions-add-generic"),
            {"assessment": assessment.pk, "questions": [item.pk]},
        )

        self.assertRedirects(response, reverse("assessments:question-bank"))
        self.assertEqual(assessment.questions.get().bank_item, item)

    def test_algorithmic_assembly_uses_matching_bank_questions(self):
        first = self.create_bank_question(statement="Questão algorítmica 1")
        second = self.create_bank_question(statement="Questão algorítmica 2")

        response = self.client.post(
            reverse("assessments:create"),
            self.assessment_data(
                assembly_method=Assessment.AssemblyMethod.ALGORITHMIC,
                desired_question_count=2,
            ),
        )

        assessment = Assessment.objects.get()
        self.assertRedirects(response, reverse("assessments:index"))
        self.assertEqual(assessment.assembly_status, Assessment.AssemblyStatus.READY)
        self.assertSetEqual(
            set(assessment.questions.values_list("bank_item_id", flat=True)),
            {first.pk, second.pk},
        )

    @patch("features.assessments.services.request_ai_json")
    def test_ai_curates_existing_bank_questions(self, ai_json):
        selected = self.create_bank_question(statement="Selecionada pela IA")
        self.create_bank_question(statement="Não selecionada pela IA")
        ai_json.return_value = {"question_ids": [selected.pk]}

        self.client.post(
            reverse("assessments:create"),
            self.assessment_data(
                assembly_method=Assessment.AssemblyMethod.AI_CURATED,
                desired_question_count=1,
                generation_prompt="Priorize raciocínio algébrico.",
            ),
        )

        assessment = Assessment.objects.get()
        self.assertEqual(assessment.questions.get().bank_item, selected)
        self.assertEqual(assessment.assembly_status, Assessment.AssemblyStatus.READY)

    @patch("features.assessments.services.request_ai_json")
    def test_ai_generates_all_questions_for_assessment(self, ai_json):
        ai_json.return_value = {
            "questions": [
                {
                    "statement": "Explique o papel do vértice.",
                    "question_type": "open_ended",
                    "options": [],
                    "correct_answer": "Indicar máximo ou mínimo.",
                    "explanation": "O vértice é o extremo da parábola.",
                    "points": 3,
                }
            ]
        }

        self.client.post(
            reverse("assessments:create"),
            self.assessment_data(
                assembly_method=Assessment.AssemblyMethod.AI_GENERATED,
                desired_question_count=1,
                generation_prompt="Crie uma questão discursiva conceitual.",
            ),
        )

        assessment = Assessment.objects.get()
        item = QuestionBankItem.objects.get()
        self.assertEqual(item.creation_method, QuestionBankItem.CreationMethod.AI_GENERATED)
        self.assertEqual(assessment.questions.get().bank_item, item)
        self.assertEqual(assessment.assembly_status, Assessment.AssemblyStatus.READY)
