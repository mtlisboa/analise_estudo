from django.db import migrations


TECHNIQUES = (
    ("active-recall", "Recordação ativa", "Recuperação da resposta sem consultar o material."),
    ("spaced-review", "Repetição espaçada", "Revisões distribuídas em intervalos crescentes."),
    ("comparative-questions", "Questões comparativas", "Comparação de conceitos, relações e diferenças."),
    ("problem-solving", "Resolução de problemas", "Aplicação de regras para chegar a uma solução."),
    ("socratic-questioning", "Questionamento socrático", "Perguntas encadeadas que explicitam o raciocínio."),
    ("scenario-application", "Aplicação em cenário", "Uso do conhecimento em uma situação contextualizada."),
)

ASSESSMENT_TYPES = (
    ("memorization", "Memorização", "active-recall"),
    ("comprehension", "Compreensão", "socratic-questioning"),
    ("deduction", "Dedução", "problem-solving"),
    ("application", "Aplicação", "scenario-application"),
    ("analysis", "Análise", "comparative-questions"),
    ("critical-thinking", "Pensamento crítico", "socratic-questioning"),
)


def seed_catalog(apps, schema_editor):
    Technique = apps.get_model("assessments", "AssessmentTechnique")
    AssessmentType = apps.get_model("assessments", "AssessmentType")
    techniques = {}
    for code, name, description in TECHNIQUES:
        technique, _ = Technique.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        techniques[code] = technique
    for code, name, default_code in ASSESSMENT_TYPES:
        AssessmentType.objects.update_or_create(
            code=code,
            defaults={"name": name, "default_technique": techniques[default_code]},
        )


class Migration(migrations.Migration):
    dependencies = [("assessments", "0001_initial")]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
