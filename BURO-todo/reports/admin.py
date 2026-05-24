from django.contrib import admin
from .models import AcademicReport

@admin.register(AcademicReport)
class AcademicReportAdmin(admin.ModelAdmin):
    list_display = ('period_label', 'date_from', 'date_to', 'status', 'is_automatic', 'generated_at')
    list_filter = ('status', 'is_automatic')
    readonly_fields = ('generated_at', 'report_data')
