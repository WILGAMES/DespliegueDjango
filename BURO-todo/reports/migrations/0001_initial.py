from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0009_add_phone_otp_enabled_otpcode'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AcademicReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_label', models.CharField(max_length=50)),
                ('date_from', models.DateField()),
                ('date_to', models.DateField()),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('is_automatic', models.BooleanField(default=False)),
                ('status', models.CharField(
                    choices=[('completed', 'Completado'), ('failed', 'Fallido')],
                    default='completed',
                    max_length=20,
                )),
                ('report_data', models.JSONField(default=dict)),
                ('generated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='generated_reports',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Reporte Académico',
                'verbose_name_plural': 'Reportes Académicos',
                'db_table': 'reporte_academico',
                'ordering': ['-generated_at'],
            },
        ),
    ]
