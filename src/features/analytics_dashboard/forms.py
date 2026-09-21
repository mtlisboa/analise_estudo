from django import forms

from .services import PERIODS, build_dashboard


class GenerateAnalysisForm(forms.Form):
    title = forms.CharField(
        label="Nome da análise",
        max_length=160,
        required=False,
        help_text="Se ficar vazio, o sistema criará um nome a partir do escopo.",
    )
    organization = forms.ChoiceField(label="Instituição", required=False)
    classroom = forms.ChoiceField(label="Turma", required=False)
    student = forms.ChoiceField(label="Aluno", required=False)
    period = forms.ChoiceField(
        label="Período analisado",
        choices=[(key, label) for key, (label, _) in PERIODS.items()],
        initial="90",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        available = build_dashboard(user, {})
        self.fields["organization"].choices = [("", "Todas as instituições")] + [
            (str(item.pk), item.name) for item in available["organizations"]
        ]
        self.fields["classroom"].choices = [("", "Todas as turmas")] + [
            (str(item.pk), f"{item.name} · {item.organization.name}")
            for item in available["classrooms"]
        ]
        self.fields["student"].choices = [("", "Todos os alunos")] + [
            (str(item.pk), item.get_full_name().strip() or item.username)
            for item in available["students"]
        ]

    @property
    def analysis_params(self) -> dict[str, str]:
        return {
            key: self.cleaned_data[key]
            for key in ("organization", "classroom", "student", "period")
        }
