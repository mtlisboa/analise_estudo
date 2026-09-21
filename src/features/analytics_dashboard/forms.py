from django import forms

from .services import PERIODS, build_dashboard


class GenerateAnalysisForm(forms.Form):
    organization = forms.ChoiceField(label="Instituição", required=False)
    group = forms.ChoiceField(label="Grupo de turmas", required=False)
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
        groups_by_id = {item.pk: item for item in available["classroom_groups"]}

        def group_path(item):
            names = [item.name]
            parent_id = item.parent_id
            visited = {item.pk}
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = groups_by_id.get(parent_id)
                if parent is None:
                    break
                names.append(parent.name)
                parent_id = parent.parent_id
            return " › ".join(reversed(names))

        self.fields["organization"].choices = [("", "Todas as instituições")] + [
            (str(item.pk), item.name) for item in available["organizations"]
        ]
        self.fields["group"].choices = [("", "Todos os grupos de turmas")] + [
            (str(item.pk), f"{item.organization.name} · {group_path(item)}")
            for item in available["classroom_groups"]
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
            for key in ("organization", "group", "classroom", "student", "period")
        }


class SaveAnalysisForm(GenerateAnalysisForm):
    title = forms.CharField(
        label="Nome da análise",
        max_length=160,
        required=False,
        help_text="Se ficar vazio, o sistema usará o escopo e o período.",
    )
    selected_students = forms.CharField(required=False, widget=forms.HiddenInput())
    selection_label = forms.CharField(required=False, max_length=160, widget=forms.HiddenInput())

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        for field_name in ("organization", "group", "classroom", "student", "period"):
            self.fields[field_name].widget = forms.HiddenInput()

    @property
    def analysis_params(self) -> dict[str, str]:
        return {
            **super().analysis_params,
            "selected_students": self.cleaned_data["selected_students"],
        }
