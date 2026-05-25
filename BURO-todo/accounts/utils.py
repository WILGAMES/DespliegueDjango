# accounts/utils.py
# PTCJMGA-158: Helper to check role permissions
# Usage: role_has_permission(request.user.role, 'beneficiary', 'create')

import logging
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.utils import timezone
from .models import Beneficiary, RolePermission, Student
from cases.models import Case


logger = logging.getLogger(__name__)


def normalize_role_name(raw_role):
    role = (raw_role or '').strip().lower()
    aliases = {
        'beneficiary': 'beneficiario',
        'beneficiario': 'beneficiario',
        'student': 'estudiante',
        'estudiante': 'estudiante',
        'professor': 'profesor',
        'profesor': 'profesor',
        'professon': 'profesor',
        'profeson': 'profesor',
        'secretary': 'secretaria',
        'secretaria': 'secretaria',
    }
    return aliases.get(role, role)


def get_user_role(user):
    if not user.is_authenticated:
        return 'Invitado'

    if isinstance(user, Beneficiary):
        return 'beneficiario'

    # Los superusuarios tienen acceso de secretaria
    if getattr(user, 'is_superuser', False):
        return 'secretaria'

    role = getattr(user, 'role', None)
    if role is None:
        if hasattr(user, 'secretary_profile'):
            return 'secretaria'
        if hasattr(user, 'professor_profile'):
            return 'profesor'
        if hasattr(user, 'student_profile'):
            return 'estudiante'
        return 'Invitado'

    return normalize_role_name(getattr(role, 'name', 'Invitado'))


def is_secretary(user):
    if isinstance(user, Beneficiary):
        return False
    if hasattr(user, 'role') and user.role is not None:
        if normalize_role_name(user.role.name) == 'secretaria':
            return True
    return hasattr(user, 'secretary_profile')


def role_has_permission(role, resource, action):
    """
    Returns True if the given role has the specified permission.
    Args:
        role: Role instance
        resource: string e.g. 'beneficiary', 'case', 'attendance'
        action: string e.g. 'create', 'read', 'assign', 'grade'
    """
    if role is None:
        return False
    return RolePermission.objects.filter(
        role=role,
        permission__resource=resource,
        permission__action=action,
    ).exists()


def validate_professor(user):
    """
    Raises PermissionDenied unless the given SystemUser has the role 'profesor'.
    """
    if isinstance(user, Beneficiary):
        raise PermissionDenied('Solo usuarios internos con rol profesor pueden ejecutar esta accion.')

    if not hasattr(user, 'role') or user.role is None:
        raise PermissionDenied('El usuario no tiene un rol asignado.')

    role_name = normalize_role_name(user.role.name)
    if role_name != 'profesor':
        raise PermissionDenied('Solo usuarios con rol profesor pueden ejecutar esta accion.')

    return True


def validate_professor_legal_room_access(user, case):
    """
    Ensures a professor can only access academic records from their LegalRoom.
    Raises PermissionDenied and logs invalid attempts.
    """
    try:
        validate_professor(user)
    except PermissionDenied:
        logger.warning(
            'Invalid academic traceability access: non-professor user_id=%s case_id=%s',
            getattr(user, 'id', None),
            getattr(case, 'id', None),
        )
        raise

    if not hasattr(user, 'professor_profile'):
        logger.warning(
            'Invalid academic traceability access: professor without profile user_id=%s case_id=%s',
            getattr(user, 'id', None),
            getattr(case, 'id', None),
        )
        raise PermissionDenied('El usuario no tiene perfil de profesor.')

    professor_room_id = getattr(user, 'room_id', None)
    case_room_id = getattr(case, 'room_id', None)

    if professor_room_id is None:
        logger.warning(
            'Invalid academic traceability access: professor without LegalRoom user_id=%s case_id=%s',
            getattr(user, 'id', None),
            getattr(case, 'id', None),
        )
        raise PermissionDenied('El profesor no tiene sala juridica asignada.')

    if professor_room_id != case_room_id:
        logger.warning(
            'Invalid academic traceability access: LegalRoom mismatch user_id=%s professor_room_id=%s case_id=%s case_room_id=%s',
            getattr(user, 'id', None),
            professor_room_id,
            getattr(case, 'id', None),
            case_room_id,
        )
        raise PermissionDenied('El profesor no puede consultar acciones academicas de otra sala juridica.')

    return True


def validate_coordinator(user):
    """
    Raises PermissionDenied unless the given SystemUser has the role 'secretaria' or is staff.
    """
    if isinstance(user, Beneficiary):
        raise PermissionDenied('Solo usuarios internos con rol secretaria pueden ejecutar esta accion.')

    if user.is_staff:
        return True

    if not hasattr(user, 'role') or user.role is None:
        raise PermissionDenied('El usuario no tiene un rol asignado.')

    role_name = normalize_role_name(user.role.name)
    if role_name != 'secretaria':
        raise PermissionDenied('Solo usuarios con rol secretaria pueden ejecutar esta accion.')

    return True


def get_case_urgency(case):
    """
    Returns urgency level for a case using due date semantics.

    - RED when overdue or 1 day or less remains.
    - YELLOW when 2-3 days remain.
    - GREEN when more than 3 days remain.
    """
    due_date = getattr(case, 'due_date', None) or getattr(case, 'legal_deadline', None)
    if due_date is None:
        return 'GREEN'

    if hasattr(due_date, 'date'):
        due_date = due_date.date()

    today = timezone.localdate()
    remaining_days = (due_date - today).days

    if remaining_days <= 1:
        return 'RED'
    if 2 <= remaining_days <= 3:
        return 'YELLOW'
    return 'GREEN'


def get_student_load(student):
    """
    Returns the number of cases currently assigned to the given student.
    Works with both Student profile instances and SystemUser instances.
    """
    if hasattr(student, 'user'):
        student_profile = student
    else:
        student_profile = getattr(student, 'student_profile', None)
    if not student_profile:
        return 0
    return Case.objects.filter(student=student_profile).count()


def get_student_load_summary(student, room=None):
    """
    Returns a summary of active cases for the given student.

    The summary includes total active cases, counts by urgency,
    and a detailed list of cases with computed urgency.
    """
    if hasattr(student, 'user'):
        student_profile = student
    else:
        student_profile = getattr(student, 'student_profile', None)
    if not student_profile:
        return {
            'total_active_cases': 0,
            'red_count': 0,
            'yellow_count': 0,
            'green_count': 0,
            'cases': [],
        }

    closed_statuses = ['Cerrado', 'closed', 'Finalizado', 'finalizado']
    active_cases_qs = student_profile.assigned_cases.exclude(status__in=closed_statuses)

    if room is not None:
        if isinstance(room, str) and room.isdigit():
            active_cases_qs = active_cases_qs.filter(room_id=int(room))
        else:
            active_cases_qs = active_cases_qs.filter(room__name__icontains=room)

    red_count = 0
    yellow_count = 0
    green_count = 0
    cases_with_urgency = []

    for case in active_cases_qs.select_related('student'):
        urgency = get_case_urgency(case)
        if urgency == 'RED':
            red_count += 1
        elif urgency == 'YELLOW':
            yellow_count += 1
        else:
            green_count += 1

        cases_with_urgency.append({
            'case': case,
            'urgency': urgency,
        })

    return {
        'total_active_cases': active_cases_qs.count(),
        'red_count': red_count,
        'yellow_count': yellow_count,
        'green_count': green_count,
        'cases': cases_with_urgency,
    }


def get_academic_dashboard(professor, room=None):
    """
    Returns academic dashboard data for a professor.

    The dashboard includes supervised students, active case urgency counts,
    and summary metrics for load and availability.
    """
    if professor is None:
        return {
            'students': [],
            'summary': {
                'avg_load': 0.0,
                'overloaded_students': 0,
                'available_students': 0,
            },
        }

    cases_qs = Case.objects.filter(professor=professor, student__isnull=False)
    if room is not None:
        if isinstance(room, str) and room.isdigit():
            cases_qs = cases_qs.filter(room_id=int(room))
        else:
            cases_qs = cases_qs.filter(room__name__icontains=room)

    student_ids = cases_qs.values_list('student_id', flat=True).distinct()
    students = Student.objects.select_related('user').filter(id__in=student_ids)
    if not students.exists():
        return {
            'students': [],
            'summary': {
                'avg_load': 0.0,
                'overloaded_students': 0,
                'available_students': 0,
            },
        }

    students_data = []
    total_active_cases = 0
    for student in students:
        load_summary = get_student_load_summary(student, room=room)
        critical_case_id = None
        critical_due_date = None
        for entry in load_summary['cases']:
            case = entry['case']
            due_date = getattr(case, 'due_date', None) or getattr(case, 'legal_deadline', None)
            if hasattr(due_date, 'date'):
                due_date = due_date.date()
            if due_date is None:
                continue
            if critical_due_date is None or due_date < critical_due_date:
                critical_due_date = due_date
                critical_case_id = case.id

        active_cases = load_summary['total_active_cases']
        students_data.append({
            'name': student.user.name,
            'total_cases': active_cases,
            'red_count': load_summary['red_count'],
            'yellow_count': load_summary['yellow_count'],
            'green_count': load_summary['green_count'],
            'partial_grade': 0.0,
            'critical_case_id': critical_case_id,
        })
        total_active_cases += active_cases

    avg_load = round(total_active_cases / len(students), 2) if students else 0.0
    overloaded_students = sum(1 for student in students_data if student['total_cases'] > avg_load)
    available_students = len(students_data) - overloaded_students

    return {
        'students': students_data,
        'summary': {
            'avg_load': avg_load,
            'overloaded_students': overloaded_students,
            'available_students': available_students,
        },
    }


def auto_assign_cases(professor_user):
    from cases.services import assign_students_to_pending_cases
    return assign_students_to_pending_cases(professor_user)

def _normalize_period(period):
    if not period:
        return None
    normalized = period.strip().lower()
    mapping = {
        'diario': 'daily',
        'semanal': 'weekly',
        'mensual': 'monthly',
    }
    return mapping.get(normalized, normalized)


def filter_cases_by_period(period, room_id=None):
    """
    Filters cases based on the specified time period using the created_at field.
    Supported periods: 'daily', 'weekly', 'monthly'.
    Returns all cases if the period is invalid.
    """
    now = timezone.now()
    queryset = Case.objects.all()

    if room_id:
        queryset = queryset.filter(room_id=room_id)
    
    normalized_period = _normalize_period(period)

    if normalized_period == 'daily':
        queryset = queryset.filter(created_at__date=now.date())
    elif normalized_period == 'weekly':
        queryset = queryset.filter(created_at__gte=now - timedelta(days=7))
    elif normalized_period == 'monthly':
        queryset = queryset.filter(created_at__gte=now - timedelta(days=30))
    
    return queryset

def get_student_metrics(student, period=None, room_id=None):
    """
    Calculates case metrics for a specific student, optionally filtered by period.
    Metrics include active, closed, and total cases.
    """
    if hasattr(student, 'user'):
        student_profile = student
    else:
        student_profile = getattr(student, 'student_profile', None)
    if not student_profile:
        return {
            'active_cases': 0,
            'closed_cases': 0,
            'total_cases': 0,
            'performance': 0.0,
        }

    # Obtener el queryset base filtrado por periodo y estudiante
    queryset = filter_cases_by_period(period, room_id).filter(student=student_profile)
    closed_statuses = ['Cerrado', 'closed', 'Finalizado', 'finalizado']
    total_cases = queryset.count()
    closed_cases = queryset.filter(status__in=closed_statuses).count()
    active_cases = total_cases - closed_cases
    performance = round((closed_cases / total_cases) * 100, 2) if total_cases else 0.0

    return {
        'active_cases': active_cases,
        'closed_cases': closed_cases,
        'total_cases': total_cases,
        'performance': performance,
    }

def get_global_metrics(period=None, room_id=None):
    """
    Calculates aggregate metrics for all cases, optionally filtered.
    """
    queryset = filter_cases_by_period(period, room_id)
    total_cases = queryset.count()
    closed_statuses = ['Cerrado', 'closed', 'Finalizado', 'finalizado']
    closed_cases = queryset.filter(status__in=closed_statuses).count()
    active_cases = total_cases - closed_cases

    students_count = Student.objects.count()
    avg_load = total_cases / students_count if students_count > 0 else 0

    return {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'closed_cases': closed_cases,
        'resolved_cases': closed_cases,
        'avg_load': round(avg_load, 2)
    }


def get_system_statistics(period=None, room=None):
    """
    Generates system-wide academic statistics for the coordinator.
    Returns summary, key indicators, and optional breakdown by room.
    """
    from .models import LegalRoom

    queryset = filter_cases_by_period(period, room)
    total_cases = queryset.count()
    closed_statuses = ['Cerrado', 'closed', 'Finalizado', 'finalizado']
    closed_cases = queryset.filter(status__in=closed_statuses).count()
    active_cases = total_cases - closed_cases
    assigned_cases = queryset.filter(student__isnull=False).count()

    students_count = Student.objects.count()
    avg_load = total_cases / students_count if students_count > 0 else 0

    # Key indicators
    resolution_rate = (closed_cases / total_cases * 100) if total_cases > 0 else 0
    assignment_rate = (assigned_cases / total_cases * 100) if total_cases > 0 else 0

    summary = {
        'total_cases': total_cases,
        'active_cases': active_cases,
        'closed_cases': closed_cases,
        'assigned_cases': assigned_cases,
        'avg_load_per_student': round(avg_load, 2),
        'resolution_rate': round(resolution_rate, 2),
        'assignment_rate': round(assignment_rate, 2),
    }

    # Breakdown by room (optional)
    breakdown_by_room = []
    if room is None:  # Only if no specific room filter
        rooms = LegalRoom.objects.all()
        for room_obj in rooms:
            room_queryset = queryset.filter(room=room_obj)
            room_total = room_queryset.count()
            room_closed = room_queryset.filter(status__in=closed_statuses).count()
            room_active = room_total - room_closed
            breakdown_by_room.append({
                'room_name': room_obj.name,
                'total_cases': room_total,
                'active_cases': room_active,
                'closed_cases': room_closed,
            })

    return {
        'summary': summary,
        'breakdown_by_room': breakdown_by_room,
    }
