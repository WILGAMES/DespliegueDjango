from django.db import transaction

from accounts.models import Student
from cases.models import AssignmentCriteriaConfig, AutomaticAssignmentLog, Case

_CLOSED_STATUSES = ['Cerrado', 'Cancelado', 'Finalizado', 'closed', 'cancelled', 'finalizado']


def _get_active_assignment_config():
    return AssignmentCriteriaConfig.objects.filter(active=True).order_by('-updated_at').first()


def _log_assignment_event(case: Case, student: Student | None, reason: str, success: bool):
    AutomaticAssignmentLog.objects.create(
        case=case,
        student=student,
        assignment_reason=reason,
        created_by_system=True,
    )


def _professor_active_case_count(professor):
    return Case.objects.filter(professor=professor).exclude(status__in=_CLOSED_STATUSES).count()


def assign_case_to_student(case: Case):
    """
    Asigna automáticamente un caso a un estudiante elegible.

    La selección se basa en:
    1. Menor carga académica activa.
    2. En empate, menor número total de casos asignados.
    3. En segundo empate, menor id de estudiante.

    Se registran logs de cada intento, incluyendo los errores de validación.
    """
    if case is None:
        return None

    if case.status != 'Pendiente':
        _log_assignment_event(
            case,
            None,
            'Caso no está pendiente de asignación automática.',
            success=False,
        )
        return None

    if case.student or case.assigned_student:
        _log_assignment_event(
            case,
            None,
            'No se asignó el caso automáticamente porque ya tiene un estudiante asignado.',
            success=False,
        )
        return None

    config = _get_active_assignment_config()
    if config and _professor_active_case_count(case.professor) >= config.max_cases_per_professor:
        _log_assignment_event(
            case,
            None,
            f'No se asignó el caso automáticamente porque el profesor alcanzó el límite de {config.max_cases_per_professor} casos.',
            success=False,
        )
        return None

    eligible_students = (
        Student.objects.filter(status__iexact='active', user__room=case.room)
        .select_related('user')
    )
    if not eligible_students.exists():
        _log_assignment_event(
            case,
            None,
            'No hay estudiantes elegibles en la misma sala jurídica para asignación automática.',
            success=False,
        )
        return None

    def _student_sort_key(student: Student):
        active_load = student.get_active_cases_count()
        total_cases = student.assigned_cases.count()
        return (active_load, total_cases, student.id)

    selected_student = min(eligible_students, key=_student_sort_key)

    case.student = selected_student
    case.assigned_student = selected_student.user
    case.status = 'Asignado'

    with transaction.atomic():
        case.save(update_fields=['student', 'assigned_student', 'status'])
        _log_assignment_event(
            case,
            selected_student,
            f'Caso asignado automáticamente al estudiante {selected_student.user.email}.',
            success=True,
        )

    return selected_student
