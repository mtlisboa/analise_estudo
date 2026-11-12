import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('institution_analysis', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='ActiveAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=120)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='institution_planning.offer')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users_manager.institutionalaccount')),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('recipient', 'offer', 'key'), name='analysis_active_alert_unique'),
            ]},
        ),
    ]
