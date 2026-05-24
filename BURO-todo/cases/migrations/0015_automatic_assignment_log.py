# Generated manually to add AutomaticAssignmentLog model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0014_assignmentcriteria_log'),
    ]

    operations = [
        migrations.CreateModel(
            name='AutomaticAssignmentLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('assignment_reason', models.TextField()),
                ('created_by_system', models.BooleanField(default=True)),
                ('case', models.ForeignKey(on_delete=models.PROTECT, related_name='automatic_assignment_logs', to='cases.case')),
                ('student', models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='automatic_assignment_logs', to='accounts.student')),
            ],
            options={
                'db_table': 'bitacora_asignacion_automatica',
                'verbose_name': 'Automatic Assignment Log',
                'verbose_name_plural': 'Automatic Assignment Logs',
                'ordering': ['-assigned_at', '-id'],
            },
        ),
    ]
