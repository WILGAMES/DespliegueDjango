from django.db import models


class AcademicReport(models.Model):
    STATUS_CHOICES = [
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
    ]

    period_label = models.CharField(max_length=50)
    date_from = models.DateField()
    date_to = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        'accounts.SystemUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_reports',
    )
    is_automatic = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    report_data = models.JSONField(default=dict)

    class Meta:
        db_table = 'reporte_academico'
        verbose_name = 'Reporte Académico'
        verbose_name_plural = 'Reportes Académicos'
        ordering = ['-generated_at']

    def __str__(self):
        origin = 'Auto' if self.is_automatic else 'Manual'
        return f'Reporte {self.period_label} ({origin}) — {self.generated_at:%Y-%m-%d}'
