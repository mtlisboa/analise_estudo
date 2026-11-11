from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("institution_planning", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="responsible_teacher",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.PROTECT,
                related_name="responsible_offers", to="institution_planning.teacher",
                verbose_name="professor responsável",
            ),
        ),
    ]
