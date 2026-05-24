import logging
from datetime import date

from django.db.models import Avg

from cases.models import AcademicAction, Case
from accounts.models import LegalRoom, Student

logger = logging.getLogger(__name__)

_CLOSED_STATUSES = ['Cerrado', 'closed', 'Finalizado', 'finalizado']


def _build_report_data(date_from: date, date_to: date) -> dict:
    cases_qs = Case.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )

    total_cases = cases_qs.count()
    closed_cases = cases_qs.filter(status__in=_CLOSED_STATUSES).count()
    active_cases = total_cases - closed_cases
    assigned_cases = cases_qs.filter(student__isnull=False).count()

    students_count = Student.objects.count()
    avg_load = round(total_cases / students_count, 2) if students_count else 0.0
    resolution_rate = round(closed_cases / total_cases * 100, 2) if total_cases else 0.0
    assignment_rate = round(assigned_cases / total_cases * 100, 2) if total_cases else 0.0

    actions_qs = AcademicAction.objects.filter(
        registered_at__date__gte=date_from,
        registered_at__date__lte=date_to,
    )
    total_actions = actions_qs.count()
    avg_grade_raw = actions_qs.aggregate(avg=Avg('grade'))['avg']
    avg_grade = round(float(avg_grade_raw), 2) if avg_grade_raw is not None else 0.0

    breakdown_by_room = []
    for room in LegalRoom.objects.all():
        room_cases = cases_qs.filter(room=room)
        room_total = room_cases.count()
        room_closed = room_cases.filter(status__in=_CLOSED_STATUSES).count()
        breakdown_by_room.append({
            'room_name': room.name,
            'total_cases': room_total,
            'active_cases': room_total - room_closed,
            'closed_cases': room_closed,
        })

    return {
        'summary': {
            'total_cases': total_cases,
            'active_cases': active_cases,
            'closed_cases': closed_cases,
            'assigned_cases': assigned_cases,
            'avg_load_per_student': avg_load,
            'resolution_rate': resolution_rate,
            'assignment_rate': assignment_rate,
            'total_academic_actions': total_actions,
            'avg_grade': avg_grade,
        },
        'breakdown_by_room': breakdown_by_room,
    }


def generate_and_save_report(
    period_label: str,
    date_from: date,
    date_to: date,
    generated_by=None,
    is_automatic: bool = False,
) -> 'reports.models.AcademicReport':
    from .models import AcademicReport

    try:
        data = _build_report_data(date_from, date_to)
        report = AcademicReport.objects.create(
            period_label=period_label,
            date_from=date_from,
            date_to=date_to,
            generated_by=generated_by,
            is_automatic=is_automatic,
            status='completed',
            report_data=data,
        )
        logger.info('Reporte %s generado (pk=%s)', period_label, report.pk)
        return report
    except Exception as exc:
        logger.error('Error generando reporte %s: %s', period_label, exc)
        raise
