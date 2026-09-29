import uuid
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("users_manager", "0010_alter_institutionalaccount_role")]
    operations = [
        migrations.CreateModel(
            name="Period",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="users_manager.organization")),
                ("name", models.CharField("período letivo", max_length=80)),
                ("starts_on", models.DateField("início")),
                ("ends_on", models.DateField("fim")),
                ("revision", models.PositiveIntegerField(default=0)),
                ("published_at", models.DateTimeField(null=True, blank=True)),
                ("published_revision", models.PositiveIntegerField(null=True, blank=True)),
            ],
            options={"ordering": ["-starts_on", "name"], "constraints": [models.UniqueConstraint(fields=["organization", "name"], name="planning_period_name")]},
        ),
        migrations.CreateModel(
            name="Offer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.UUIDField("código da oferta", default=uuid.uuid4, unique=True, editable=False)),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.period", related_name="offers")),
                ("name", models.CharField("turma", max_length=100)),
                ("grade", models.CharField("série / etapa", max_length=60)),
                ("shift", models.CharField("turno", max_length=10, choices=[("MORNING", "Manhã"), ("AFTERNOON", "Tarde"), ("EVENING", "Noite"), ("FULL_TIME", "Integral")])),
                ("capacity", models.PositiveSmallIntegerField("vagas", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)])),
                ("classroom", models.OneToOneField(to="users_manager.classroom", null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planning_offer")),
                ("published_members", models.JSONField(default=list, blank=True)),
                ("published_roster", models.JSONField(default=list, blank=True)),
                ("published_schedule", models.JSONField(default=list, blank=True)),
            ],
            options={"ordering": ["grade", "shift", "name"], "constraints": [models.UniqueConstraint(fields=["period", "name"], name="planning_offer_name")]},
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.period", related_name="students")),
                ("registration", models.CharField("matrícula", max_length=40)),
                ("name", models.CharField("nome", max_length=150)),
                ("grade", models.CharField("série / etapa", max_length=60)),
                ("shift", models.CharField("turno", max_length=10, choices=[("MORNING", "Manhã"), ("AFTERNOON", "Tarde"), ("EVENING", "Noite"), ("FULL_TIME", "Integral")])),
                ("previous_cohort", models.CharField("turma anterior (inclua ano e escola)", max_length=120, blank=True)),
                ("offer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="institution_planning.offer", null=True, blank=True, related_name="students")),
                ("locked", models.BooleanField("fixar distribuição", default=False)),
            ],
            options={"ordering": ["name", "registration"], "constraints": [models.UniqueConstraint(fields=["period", "registration"], name="planning_student_registration")]},
        ),
        migrations.CreateModel(
            name="Slot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.period", related_name="slots")),
                ("weekday", models.PositiveSmallIntegerField("dia", choices=[(1, "Segunda"), (2, "Terça"), (3, "Quarta"), (4, "Quinta"), (5, "Sexta"), (6, "Sábado"), (7, "Domingo")])),
                ("starts_at", models.TimeField("início")),
                ("ends_at", models.TimeField("fim")),
                ("shift", models.CharField("turno", max_length=10, choices=[("MORNING", "Manhã"), ("AFTERNOON", "Tarde"), ("EVENING", "Noite"), ("FULL_TIME", "Integral")])),
            ],
            options={"ordering": ["weekday", "starts_at"], "constraints": [models.UniqueConstraint(fields=["period", "weekday", "starts_at", "ends_at", "shift"], name="planning_slot_unique")]},
        ),
        migrations.CreateModel(
            name="Teacher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.period", related_name="teachers")),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="users_manager.institutionalaccount")),
                ("subjects", models.CharField("disciplinas (separadas por vírgula)", max_length=500)),
                ("max_lessons", models.PositiveSmallIntegerField("máximo de aulas por semana", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("availability", models.ManyToManyField(to="institution_planning.slot", blank=True, verbose_name="horários disponíveis")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=["period", "account"], name="planning_teacher_unique")]},
        ),
        migrations.CreateModel(
            name="Requirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("offer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.offer", related_name="requirements")),
                ("subject", models.CharField("disciplina", max_length=80)),
                ("weekly_lessons", models.PositiveSmallIntegerField("aulas semanais", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(40)])),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="institution_planning.teacher", null=True, blank=True, related_name="requirements")),
                ("locked", models.BooleanField("fixar professor", default=False)),
            ],
            options={"ordering": ["offer__name", "subject"], "constraints": [models.UniqueConstraint(fields=["offer", "subject"], name="planning_requirement_unique")]},
        ),
        migrations.CreateModel(
            name="Lesson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="institution_planning.requirement", related_name="lessons")),
                ("slot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="institution_planning.slot", related_name="lessons")),
                ("locked", models.BooleanField("fixar horário", default=False)),
            ],
            options={"ordering": ["slot__weekday", "slot__starts_at", "requirement__offer__name"], "constraints": [models.UniqueConstraint(fields=["requirement", "slot"], name="planning_lesson_unique")]},
        ),
    ]
