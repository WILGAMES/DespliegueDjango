# Generated manually to add AssignmentCriteriaConfig model

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0012_academicaction_status_systemlog'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssignmentCriteriaConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_cases_per_professor', models.IntegerField(help_text='Número máximo de casos que puede tener asignado un profesor.', validators=[MinValueValidator(1)])),
                ('prioritize_same_room', models.BooleanField(default=True)),
                ('balance_workload', models.BooleanField(default=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'criterios_asignacion',
                'verbose_name': 'Assignment Criteria Config',
                'verbose_name_plural': 'Assignment Criteria Configs',
                'constraints': [
                    models.UniqueConstraint(
                        fields=['active'],
                        condition=models.Q(active=True),
                        name='unique_active_assignment_criteria'
                    )
                ],
            },
        ),
    ]
