import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from features.users_manager.models import Classroom, InstitutionalAccount


DAYS = [(1, "Segunda"), (2, "Terça"), (3, "Quarta"), (4, "Quinta"),
        (5, "Sexta"), (6, "Sábado"), (7, "Domingo")]


class Period(models.Model):
    organization = models.ForeignKey("users_manager.Organization", on_delete=models.CASCADE)
    name = models.CharField("período letivo", max_length=80)
    starts_on = models.DateField("início")
    ends_on = models.DateField("fim")
    revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    published_revision = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-starts_on", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="planning_period_name")]

    def clean(self):
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValidationError("O fim deve ser igual ou posterior ao início.")

    def __str__(self):
        return self.name


class Offer(models.Model):
    code = models.UUIDField("código da oferta", default=uuid.uuid4, unique=True, editable=False)
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="offers")
    name = models.CharField("turma", max_length=100)
    grade = models.CharField("série / etapa", max_length=60)
    shift = models.CharField("turno", max_length=10, choices=Classroom.Shift.choices)
    capacity = models.PositiveSmallIntegerField("vagas", validators=[MinValueValidator(1), MaxValueValidator(200)])
    classroom = models.OneToOneField("users_manager.Classroom", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="planning_offer")
    # Only memberships created/adopted by this planner may be removed on republish.
    published_members = models.JSONField(default=list, blank=True)
    published_roster = models.JSONField(default=list, blank=True)
    published_schedule = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["grade", "shift", "name"]
        constraints = [models.UniqueConstraint(fields=["period", "name"], name="planning_offer_name")]

    def clean(self):
        self.grade = self.grade.strip().upper()
        if self.pk and self.capacity is not None and self.students.count() > self.capacity:
            raise ValidationError("A capacidade não pode ficar abaixo da quantidade de alunos.")
        if self.pk and self.students.exclude(grade=self.grade, shift=self.shift).exists():
            raise ValidationError("Transfira os alunos antes de alterar série ou turno.")
        if self.classroom_id and self.classroom.organization_id != self.period.organization_id:
            raise ValidationError("A turma pertence a outra instituição.")

    def __str__(self):
        return f"{self.name} · {self.grade} · {self.get_shift_display()}"


class Student(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="students")
    registration = models.CharField("matrícula", max_length=40)
    name = models.CharField("nome", max_length=150)
    grade = models.CharField("série / etapa", max_length=60)
    shift = models.CharField("turno", max_length=10, choices=Classroom.Shift.choices)
    previous_cohort = models.CharField("turma anterior (inclua ano e escola)", max_length=120, blank=True)
    offer = models.ForeignKey(Offer, null=True, blank=True, on_delete=models.PROTECT, related_name="students")
    locked = models.BooleanField("fixar distribuição", default=False)

    class Meta:
        ordering = ["name", "registration"]
        constraints = [models.UniqueConstraint(fields=["period", "registration"], name="planning_student_registration")]

    def clean(self):
        from features.accounts.institutional import normalize_registration
        self.registration = normalize_registration(self.registration)
        self.grade = self.grade.strip().upper()
        if self.offer_id:
            if (self.offer.period_id != self.period_id or self.offer.grade != self.grade
                    or self.offer.shift != self.shift):
                raise ValidationError("A oferta deve ser do mesmo período, série e turno.")
            if self.offer.students.exclude(pk=self.pk).count() >= self.offer.capacity:
                raise ValidationError("A turma não tem vagas.")
        if self.locked and not self.offer_id:
            raise ValidationError("Escolha uma turma antes de fixar o aluno.")
        if InstitutionalAccount.objects.filter(organization=self.period.organization,
                registration=self.registration).exclude(role="STUDENT").exists():
            raise ValidationError("Esta matrícula pertence a outro perfil institucional.")

    def __str__(self):
        return f"{self.name} · {self.registration}"


class Slot(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="slots")
    weekday = models.PositiveSmallIntegerField("dia", choices=DAYS)
    starts_at = models.TimeField("início")
    ends_at = models.TimeField("fim")
    shift = models.CharField("turno", max_length=10, choices=Classroom.Shift.choices)

    class Meta:
        ordering = ["weekday", "starts_at"]
        constraints = [models.UniqueConstraint(fields=["period", "weekday", "starts_at", "ends_at", "shift"],
                                              name="planning_slot_unique")]

    def clean(self):
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError("O horário final deve ser posterior ao inicial.")
        if self.pk and self.lessons.exists():
            old = Slot.objects.get(pk=self.pk)
            if any(getattr(old, k) != getattr(self, k) for k in ("weekday", "starts_at", "ends_at", "shift")):
                raise ValidationError("Remova as aulas deste horário antes de alterá-lo.")

    def __str__(self):
        return f"{self.get_weekday_display()} {self.starts_at:%H:%M}–{self.ends_at:%H:%M} · {self.get_shift_display()}"


class Teacher(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name="teachers")
    account = models.ForeignKey("users_manager.InstitutionalAccount", on_delete=models.PROTECT)
    subjects = models.CharField("disciplinas (separadas por vírgula)", max_length=500)
    max_lessons = models.PositiveSmallIntegerField("máximo de aulas por semana",
        validators=[MinValueValidator(1), MaxValueValidator(100)])
    availability = models.ManyToManyField(Slot, blank=True, verbose_name="horários disponíveis")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["period", "account"], name="planning_teacher_unique")]

    def clean(self):
        self.subjects = ", ".join(sorted({v.strip().upper() for v in self.subjects.split(",") if v.strip()}))
        if not self.subjects:
            raise ValidationError("Informe pelo menos uma disciplina.")
        if self.account_id and (self.account.organization_id != self.period.organization_id
                or self.account.role != "TEACHER" or not self.account.user.is_active):
            raise ValidationError("Selecione um professor ativo desta instituição.")

    def teaches(self, subject):
        return subject.strip().upper() in self.subjects.split(", ")

    def __str__(self):
        return self.account.user.get_full_name() or self.account.registration


class Requirement(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="requirements")
    subject = models.CharField("disciplina", max_length=80)
    weekly_lessons = models.PositiveSmallIntegerField("aulas semanais",
        validators=[MinValueValidator(1), MaxValueValidator(40)])
    teacher = models.ForeignKey(Teacher, null=True, blank=True, on_delete=models.PROTECT, related_name="requirements")
    locked = models.BooleanField("fixar professor", default=False)

    class Meta:
        ordering = ["offer__name", "subject"]
        constraints = [models.UniqueConstraint(fields=["offer", "subject"], name="planning_requirement_unique")]

    def clean(self):
        self.subject = self.subject.strip().upper()
        if self.offer_id and self.teacher_id and (self.teacher.period_id != self.offer.period_id or not self.teacher.teaches(self.subject)):
            raise ValidationError("O professor deve ser habilitado na disciplina e pertencer ao período.")
        if self.locked and not self.teacher_id:
            raise ValidationError("Escolha um professor antes de fixar.")
        if self.pk and self.weekly_lessons is not None and self.lessons.count() > self.weekly_lessons:
            raise ValidationError("Remova aulas antes de reduzir a carga semanal.")

    def __str__(self):
        return f"{self.offer.name} · {self.subject}"


class Lesson(models.Model):
    requirement = models.ForeignKey(Requirement, on_delete=models.CASCADE, related_name="lessons")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="lessons")
    locked = models.BooleanField("fixar horário", default=False)

    class Meta:
        ordering = ["slot__weekday", "slot__starts_at", "requirement__offer__name"]
        constraints = [models.UniqueConstraint(fields=["requirement", "slot"], name="planning_lesson_unique")]

    def clean(self):
        if self.requirement_id and self.slot_id:
            from .services import validate_lesson
            validate_lesson(self)

    def __str__(self):
        return f"{self.requirement} · {self.slot}"
