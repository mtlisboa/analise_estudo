from django import forms

from features.users_manager.models import InstitutionalAccount
from .models import Period, Offer, Student, Slot, Teacher, Requirement, Lesson


class RevisionForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class BatchForm(RevisionForm):
    students = forms.CharField(label="Lista de alunos", max_length=200000,
        widget=forms.Textarea(attrs={"rows": 9, "spellcheck": "false"}),
        help_text="Uma linha por aluno: matrícula;nome;série;turno;turma anterior (opcional). "
                  "Turnos: MORNING, AFTERNOON, EVENING ou FULL_TIME. "
                  "Exemplo: 202601;Ana Silva;7º ANO;MORNING;2025 / Escola A / 6º A. "
                  "Este cadastro monta a lista escolar; acessos de login continuam gerenciados pelo administrativo.")


class ScopedForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, period, **kwargs):
        super().__init__(*args, **kwargs)
        self.period = period
        self.fields["revision"].initial = period.revision
        if hasattr(self.instance, "period_id"):
            self.instance.period = period
        self.scope()

    def scope(self):
        pass


class PeriodForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = ["name", "starts_on", "ends_on"]
        widgets = {k: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
                   for k in ("starts_on", "ends_on")}


class PeriodEditForm(ScopedForm):
    class Meta(PeriodForm.Meta):
        pass


class OfferForm(ScopedForm):
    class Meta:
        model = Offer
        fields = ["name", "grade", "shift", "capacity"]


class StudentForm(ScopedForm):
    class Meta:
        model = Student
        fields = ["registration", "name", "grade", "shift", "previous_cohort", "offer", "locked"]

    def scope(self):
        self.fields["offer"].queryset = self.period.offers.all()
        if self.instance.pk:
            self.fields["registration"].disabled = True


class SlotForm(ScopedForm):
    class Meta:
        model = Slot
        fields = ["weekday", "starts_at", "ends_at", "shift"]
        widgets = {k: forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
                   for k in ("starts_at", "ends_at")}


class TeacherForm(ScopedForm):
    class Meta:
        model = Teacher
        fields = ["account", "subjects", "max_lessons", "availability"]
        widgets = {"availability": forms.CheckboxSelectMultiple}

    def scope(self):
        self.fields["account"].queryset = InstitutionalAccount.objects.filter(
            organization=self.period.organization, role="TEACHER", user__is_active=True).select_related("user")
        self.fields["availability"].queryset = self.period.slots.all()


class RequirementForm(ScopedForm):
    class Meta:
        model = Requirement
        fields = ["offer", "subject", "weekly_lessons", "teacher", "locked"]

    def scope(self):
        self.fields["offer"].queryset = self.period.offers.all()
        self.fields["teacher"].queryset = self.period.teachers.select_related("account__user")


class LessonForm(ScopedForm):
    class Meta:
        model = Lesson
        fields = ["requirement", "slot", "locked"]

    def scope(self):
        self.fields["requirement"].queryset = Requirement.objects.filter(offer__period=self.period)
        self.fields["slot"].queryset = self.period.slots.all()


FORMS = {"period": PeriodEditForm, "offer": OfferForm, "student": StudentForm,
         "slot": SlotForm, "teacher": TeacherForm, "requirement": RequirementForm, "lesson": LessonForm}
LABELS = {"period": "Período", "offer": "Oferta de turma", "student": "Aluno",
          "slot": "Horário", "teacher": "Professor", "requirement": "Disciplina da turma", "lesson": "Aula"}
