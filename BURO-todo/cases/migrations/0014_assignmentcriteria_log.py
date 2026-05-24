# Generated manually to add AssignmentCriteriaLog model

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0013_assignmentcriteria_config'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AssignmentCriteriaLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_name', models.CharField(max_length=100)),
                ('old_value', models.TextField(blank=True, null=True)),
                ('new_value', models.TextField(blank=True, null=True)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(on_delete=models.PROTECT, related_name='assignment_criteria_changes', to=settings.AUTH_USER_MODEL)),
                ('criteria', models.ForeignKey(on_delete=models.CASCADE, related_name='change_logs', to='cases.assignmentcriteriaconfig')),
            ],
            options={
                'db_table': 'bitacora_criterios_asignacion',
                'verbose_name': 'Assignment Criteria Log',
                'verbose_name_plural': 'Assignment Criteria Logs',
                'ordering': ['-changed_at', '-id'],
            },
        ),
    ]
