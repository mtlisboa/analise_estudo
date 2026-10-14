from .diagnostics import DiagnosticFields
from .sharing_forms import TeacherSharingMixin
from .bank_access import available_questions
from django import forms
from django.db import transaction
from django.db.models import Max

from .image_forms import QuestionImagesMixin
from .models import (
    Assessment,
    AssessmentTechnique,
    AssessmentType,
    Question,
    QuestionBankItem,
)


class AssessmentForm(forms.ModelForm):
    observations = forms.CharField(
        label="Observações e restrições",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Digite uma observação ou restrição e pressione Enter",
            }
        ),
        help_text="Adicione um item por linha.",
    )
    assessment_types = forms.ModelMultipleChoiceField(
        label="Tipos de questão avaliativa",
        queryset=AssessmentType.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Selecione uma ou mais habilidades que a avaliação deve medir.",
    )
    technique = forms.ModelChoiceField(
        label="Técnica avaliativa",
        queryset=AssessmentTechnique.objects.none(),
        required=False,
        empty_label="Selecionar automaticamente",
        help_text="Sem seleção manual, será aplicada a técnica padrão do primeiro tipo escolhido.",
    )

    class Meta:
        model = Assessment
        fields = (
            "subject",
            "topic",
            "observations",
            "assessment_types",
            "technique",
            "assembly_method",
            "desired_question_count",
            "generation_prompt",
        )
        widgets = {
            "subject": forms.TextInput(attrs={"placeholder": "Ex.: Matemática"}),
            "topic": forms.TextInput(attrs={"placeholder": "Ex.: Funções quadráticas"}),
            "generation_prompt": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Ex.: priorize situações-problema e dificuldade intermediária",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assessment_types"].queryset = AssessmentType.objects.select_related(
            "default_technique"
        )
        self.fields["technique"].queryset = AssessmentTechnique.objects.all()
        self.fields["assembly_method"].required = False
        self.fields["desired_question_count"].required = False
        if self.instance.pk and not self.is_bound:
            self.initial["observations"] = "\n".join(self.instance.observations)
            if self.instance.technique_selected_automatically:
                self.initial["technique"] = None

    def clean_subject(self) -> str:
        return self.cleaned_data["subject"].strip()

    def clean_topic(self) -> str:
        return self.cleaned_data["topic"].strip()

    def clean_observations(self) -> list[str]:
        raw_value = self.cleaned_data.get("observations", "")
        return list(dict.fromkeys(line.strip() for line in raw_value.splitlines() if line.strip()))

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("assembly_method") or Assessment.AssemblyMethod.MANUAL
        count = cleaned_data.get("desired_question_count") or 0
        prompt = cleaned_data.get("generation_prompt", "").strip()
        if method != Assessment.AssemblyMethod.MANUAL and count < 1:
            self.add_error(
                "desired_question_count",
                "Informe quantas questões devem entrar na avaliação.",
            )
        if method in {
            Assessment.AssemblyMethod.AI_CURATED,
            Assessment.AssemblyMethod.AI_GENERATED,
        } and not prompt:
            self.add_error(
                "generation_prompt",
                "Descreva para a IA como a avaliação deve ser montada.",
            )
        cleaned_data["generation_prompt"] = prompt
        cleaned_data["assembly_method"] = method
        cleaned_data["desired_question_count"] = count
        return cleaned_data

    @transaction.atomic
    def save(self, owner=None) -> Assessment:
        assessment = super().save(commit=False)
        if owner is not None:
            assessment.owner = owner

        selected_types = list(self.cleaned_data["assessment_types"])
        selected_technique = self.cleaned_data.get("technique")
        if selected_technique is None:
            selected_technique = selected_types[0].default_technique
            assessment.technique_selected_automatically = True
        else:
            assessment.technique_selected_automatically = False

        assessment.technique = selected_technique
        assessment.save()
        assessment.assessment_types.set(selected_types)
        return assessment


class QuestionForm(DiagnosticFields, TeacherSharingMixin, QuestionImagesMixin, forms.ModelForm):
    options = forms.CharField(
        label="Alternativas",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Digite uma alternativa por linha",
            }
        ),
        help_text="Para múltipla escolha, adicione pelo menos duas alternativas.",
    )

    class Meta:
        model = Question
        fields = (
            "question_type",
            "support_text",
            "statement",
            "options",
            "correct_answer",
            "explanation",
            "points",
        )
        widgets = {
            "support_text": forms.Textarea(attrs={"rows": 4}),
            "statement": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Escreva o enunciado da questão"}
            ),
            "correct_answer": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Informe o gabarito ou a resposta esperada"}
            ),
            "explanation": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Explique por que essa é a resposta correta"}
            ),
            "points": forms.NumberInput(attrs={"min": "0.01", "step": "0.25"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure_images()

    def clean_statement(self) -> str:
        return self.cleaned_data["statement"].strip()

    def clean_options(self) -> list[str]:
        raw_value = self.cleaned_data.get("options", "")
        return list(dict.fromkeys(line.strip() for line in raw_value.splitlines() if line.strip()))

    def clean_correct_answer(self) -> str:
        return self.cleaned_data.get("correct_answer", "").strip()

    def clean_explanation(self) -> str:
        return self.cleaned_data.get("explanation", "").strip()

    def clean(self):
        cleaned_data = super().clean()
        question_type = cleaned_data.get("question_type")
        options = cleaned_data.get("options", [])
        correct_answer = cleaned_data.get("correct_answer", "")
        if question_type == Question.Type.MULTIPLE_CHOICE:
            if len(options) < 2:
                self.add_error("options", "Adicione pelo menos duas alternativas.")
            if not correct_answer:
                self.add_error("correct_answer", "Informe a alternativa correta.")
            elif correct_answer not in options:
                self.add_error(
                    "correct_answer",
                    "O gabarito deve ser idêntico a uma das alternativas.",
                )
        elif question_type == Question.Type.OPEN_ENDED:
            cleaned_data["options"] = []
        return self.validate_images(cleaned_data)

    @transaction.atomic
    def save(self, assessment: Assessment) -> Question:
        question = super().save(commit=False)
        question.assessment = assessment
        bank_item = QuestionBankItem(
            owner=assessment.owner,
            subject=assessment.subject,
            topic=assessment.topic,
            support_text=question.support_text,
            diagnostic_metadata=question.diagnostic_metadata,
            statement=question.statement,
            question_type=question.question_type,
            options=question.options,
            correct_answer=question.correct_answer,
            explanation=question.explanation,
            default_points=question.points,
            creation_method=QuestionBankItem.CreationMethod.MANUAL,
        )
        self.apply_sharing(bank_item, assessment.owner)
        bank_item.save()
        self.save_images(bank_item, assessment.owner)
        question.bank_item = bank_item
        last_order = assessment.questions.aggregate(last=Max("order"))["last"] or 0
        question.order = last_order + 1
        question.save()
        question.images.set(bank_item.images.all())
        assessment.assembly_status = Assessment.AssemblyStatus.READY
        assessment.assembly_notes = "Questão adicionada manualmente."
        assessment.save(update_fields=("assembly_status", "assembly_notes", "updated_at"))
        return question


class QuestionBankItemForm(DiagnosticFields, TeacherSharingMixin, QuestionImagesMixin, forms.ModelForm):
    options = forms.CharField(
        label="Alternativas",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Uma alternativa por linha"}),
    )

    class Meta:
        model = QuestionBankItem
        fields = (
            "title",
            "subject",
            "topic",
            "question_type",
            "support_text",
            "statement",
            "options",
            "correct_answer",
            "explanation",
            "default_points",
        )
        widgets = {
            "support_text": forms.Textarea(attrs={"rows": 4}),
            "statement": forms.Textarea(attrs={"rows": 4}),
            "correct_answer": forms.Textarea(attrs={"rows": 2}),
            "explanation": forms.Textarea(attrs={"rows": 3}),
            "default_points": forms.NumberInput(attrs={"min": "0.01", "step": "0.25"}),
        }

    def __init__(self, *args, source=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure_images(source)
        if self.instance.pk and not self.is_bound:
            self.initial["options"] = "\n".join(self.instance.options)

    def clean_options(self):
        raw = self.cleaned_data.get("options", "")
        return list(dict.fromkeys(item.strip() for item in raw.splitlines() if item.strip()))

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("question_type") == Question.Type.MULTIPLE_CHOICE:
            options = cleaned_data.get("options", [])
            answer = cleaned_data.get("correct_answer", "").strip()
            if len(options) < 2:
                self.add_error("options", "Adicione pelo menos duas alternativas.")
            if answer not in options:
                self.add_error(
                    "correct_answer",
                    "O gabarito deve ser idêntico a uma das alternativas.",
                )
        else:
            cleaned_data["options"] = []
        return self.validate_images(cleaned_data)

    @transaction.atomic
    def save_for(self, owner, *, source=None, creation_method=None):
        item = super().save(commit=False)
        item.owner = owner
        self.apply_sharing(item, owner)
        if source is not None:
            item.source_question = source
            item.creation_method = creation_method or QuestionBankItem.CreationMethod.DERIVED
        item.save()
        if source is not None:
            item.images.set(source.images.all())
        self.save_images(item, owner)
        return item


class AddBankQuestionsForm(forms.Form):
    title = forms.CharField(label='Título da nova avaliação (se não escolher uma existente)', max_length=160, required=False)
    assessment = forms.ModelChoiceField(
        label="Atividade ou prova de destino", required=False, empty_label="Criar avaliação com as questões selecionadas",
        queryset=Assessment.objects.none(),
    )
    questions = forms.ModelMultipleChoiceField(
        label="Questões do banco",
        queryset=QuestionBankItem.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assessment"].queryset = Assessment.objects.filter(owner=owner)
        self.fields["questions"].queryset = available_questions(owner)


class AIGenerateQuestionForm(TeacherSharingMixin, forms.Form):
    subject = forms.CharField(label="Matéria", max_length=120)
    topic = forms.CharField(label="Assunto", max_length=160)
    instructions = forms.CharField(
        label="Pedido para a IA",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Informe formato, dificuldade, habilidade e restrições desejadas.",
    )


class AIEditQuestionForm(TeacherSharingMixin, forms.Form):
    instructions = forms.CharField(
        label="Como a IA deve editar esta questão?",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
