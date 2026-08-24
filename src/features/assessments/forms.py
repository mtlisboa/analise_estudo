from django import forms
from django.db import transaction

from .models import Assessment, AssessmentTechnique, AssessmentType


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
        fields = ("subject", "topic", "observations", "assessment_types", "technique")
        widgets = {
            "subject": forms.TextInput(attrs={"placeholder": "Ex.: Matemática"}),
            "topic": forms.TextInput(attrs={"placeholder": "Ex.: Funções quadráticas"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assessment_types"].queryset = AssessmentType.objects.select_related(
            "default_technique"
        )
        self.fields["technique"].queryset = AssessmentTechnique.objects.all()
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
