import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def group_existing_classrooms(apps, schema_editor):
    Classroom = apps.get_model("users_manager", "Classroom")
    ClassroomGroup = apps.get_model("users_manager", "ClassroomGroup")

    organization_ids = Classroom.objects.values_list("organization_id", flat=True).distinct()
    for organization_id in organization_ids:
        first_classroom = Classroom.objects.filter(organization_id=organization_id).first()
        if first_classroom is None:
            continue
        group, _ = ClassroomGroup.objects.get_or_create(
            organization_id=organization_id,
            name="Turmas gerais",
            defaults={"created_by_id": first_classroom.owner_id},
        )
        Classroom.objects.filter(organization_id=organization_id, group__isnull=True).update(
            group=group
        )


class Migration(migrations.Migration):
    dependencies = [
        ("users_manager", "0003_classroomtest_organization_classroom_organization_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassroomGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, verbose_name="nome")),
                ("description", models.TextField(blank=True, verbose_name="descrição")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_classroom_groups",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criado por",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="classroom_groups",
                        to="users_manager.organization",
                        verbose_name="organização",
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "name"),
                        name="unique_classroom_group_name_per_organization",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="classroom",
            name="letter",
            field=models.CharField(blank=True, max_length=10, verbose_name="letra"),
        ),
        migrations.AddField(
            model_name="classroom",
            name="shift",
            field=models.CharField(
                choices=[
                    ("MORNING", "Manhã"),
                    ("AFTERNOON", "Tarde"),
                    ("EVENING", "Noite"),
                    ("FULL_TIME", "Integral"),
                ],
                default="MORNING",
                max_length=10,
                verbose_name="turno",
            ),
        ),
        migrations.AddField(
            model_name="classroom",
            name="group",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="classrooms",
                to="users_manager.classroomgroup",
                verbose_name="grupo de turmas",
            ),
        ),
        migrations.RunPython(group_existing_classrooms, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="classroom",
            name="group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="classrooms",
                to="users_manager.classroomgroup",
                verbose_name="grupo de turmas",
            ),
        ),
        migrations.AlterModelOptions(
            name="classroom",
            options={"ordering": ("shift", "letter", "name")},
        ),
    ]
