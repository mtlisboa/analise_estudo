from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_system_role")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="app_goal",
            field=models.CharField(blank=True, choices=[("IMPROVE_PERFORMANCE", "Melhorar meu desempenho"), ("ORGANIZE_STUDIES", "Organizar meus estudos"), ("PREPARE_EXAM", "Preparar-me para uma prova"), ("TEACH_OR_MANAGE", "Ensinar ou acompanhar alunos"), ("SELF_KNOWLEDGE", "Entender meus pontos fortes e dificuldades"), ("OTHER", "Outro objetivo")], max_length=24, verbose_name="objetivo com o aplicativo"),
        ),
        migrations.AddField(model_name="user", name="app_goal_details", field=models.CharField(blank=True, max_length=240, verbose_name="detalhes do objetivo")),
        migrations.AddField(
            model_name="user",
            name="diagnostic_test_choice",
            field=models.CharField(blank=True, choices=[("LATER", "Deixar para depois"), ("STARTED", "Iniciar agora")], max_length=8, verbose_name="escolha do teste diagnóstico"),
        ),
        migrations.AddField(
            model_name="user",
            name="discovery_source",
            field=models.CharField(blank=True, choices=[("RECOMMENDATION", "Indicação de alguém"), ("SOCIAL_MEDIA", "Redes sociais"), ("SEARCH", "Pesquisa na internet"), ("SCHOOL", "Escola ou faculdade"), ("WORK", "Trabalho"), ("EVENT", "Evento ou comunidade"), ("OTHER", "Outro")], max_length=20, verbose_name="como conheceu a plataforma"),
        ),
        migrations.AddField(
            model_name="user",
            name="education_level",
            field=models.CharField(blank=True, choices=[("ELEMENTARY", "Ensino fundamental"), ("HIGH_SCHOOL", "Ensino médio"), ("TECHNICAL", "Ensino técnico"), ("UNDERGRADUATE", "Graduação"), ("POSTGRADUATE", "Pós-graduação"), ("OTHER", "Outro"), ("PREFER_NOT_TO_SAY", "Prefiro não informar")], max_length=20, verbose_name="grau de escolaridade"),
        ),
        migrations.AddField(model_name="user", name="onboarding_completed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="user",
            name="onboarding_role",
            field=models.CharField(blank=True, choices=[("STUDENT", "Aluno"), ("TEACHER", "Professor"), ("MANAGER", "Gestor educacional"), ("GUARDIAN", "Responsável por aluno"), ("OTHER", "Outro")], max_length=16, verbose_name="perfil informado no onboarding"),
        ),
    ]
