"""Assignment service for automatic case assignment.

This module centralizes the automatic-assignment logic so it can be
reused from views, management commands or tests. The service assigns
students to pending cases while respecting the active
`AssignmentCriteriaConfig` when present.

Rules implemented:
- If an active `AssignmentCriteriaConfig` exists, its values are applied.
- `max_cases_per_professor`: no assignment will make a professor exceed this limit.
- `prioritize_same_room`: when True, prefer students who already have cases
  in the same `LegalRoom` as the pending case.
- `balance_workload`: when True, pick the student with the smallest current
  active-case load; otherwise pick the first eligible student.

If no active configuration is found the service falls back to the
previous behaviour: choose the student with lowest load.
"""

from typing import List

from django.db import transaction


def _get_active_config():
    from cases.models import AssignmentCriteriaConfig

    return AssignmentCriteriaConfig.objects.filter(active=True).order_by('-updated_at').first()


def assign_students_to_pending_cases(professor_user) -> List[object]:
    """Assign students to pending cases applying assignment criteria.

    Arguments:
        professor_user: the SystemUser instance representing the professor
                        who triggers the assignment (used for logging).

    Returns:
        A list with the Case instances that were assigned.
    """
    # Imports inside function to avoid circular import problems at module load.
    from notifications.services import send_notification
    from cases.models import Case, CaseLog, AssignmentCriteriaConfig
    from accounts.models import Student
    from accounts.utils import validate_professor, get_student_load

    validate_professor(professor_user)

    config = _get_active_config()

    pending_cases = Case.objects.filter(status='Pendiente', student__isnull=True).order_by('created_at', 'id')
    if not pending_cases.exists():
        return []

    students = list(Student.objects.select_related('user').all())
    if not students:
        return []

    # Compute current loads per student (active cases assigned to that student)
    current_loads = {s.id: get_student_load(s) for s in students}

    # Compute active case counts per professor to enforce max_cases_per_professor
    professor_active_counts = {}
    for case in Case.objects.exclude(status__in=['Cerrado']).select_related('professor').all():
        prof = getattr(case, 'professor', None)
        if prof:
            professor_active_counts[prof.id] = professor_active_counts.get(prof.id, 0) + 1

    assigned_cases = []

    for case in pending_cases:
        case_prof = getattr(case, 'professor', None)

        # Enforce max_cases_per_professor if config present
        if config and config.max_cases_per_professor:
            prof_count = professor_active_counts.get(case_prof.id, 0) if case_prof else 0
            if prof_count >= config.max_cases_per_professor:
                # Skip this case for now — professor reached capacity
                CaseLog.objects.create(
                    case=case,
                    event_type='error_asignacion',
                    description=f'No se asignó: el profesor {case_prof} alcanzó el límite de casos ({config.max_cases_per_professor}).',
                    executed_by=professor_user,
                )
                continue

        # Build candidate list
        candidates = students

        # If prioritize_same_room, prefer students with active cases in the same room
        if config and config.prioritize_same_room:
            same_room_candidates = []
            for s in students:
                if Case.objects.filter(student=s, room=case.room).exists():
                    same_room_candidates.append(s)
            if same_room_candidates:
                candidates = same_room_candidates

        # Select by workload or by first-available depending on config
        if config is None or config.balance_workload:
            # choose the student with minimal current load among candidates
            selected_student = min(candidates, key=lambda s: current_loads.get(s.id, 0))
        else:
            selected_student = candidates[0]

        # Persist the assignment inside an atomic block
        with transaction.atomic():
            case.student = selected_student
            case.status = 'Asignado'
            case.save()

            # Update in-memory counters
            current_loads[selected_student.id] = current_loads.get(selected_student.id, 0) + 1
            if case_prof:
                professor_active_counts[case_prof.id] = professor_active_counts.get(case_prof.id, 0) + 1

            assigned_cases.append(case)

            # Log and notify (best-effort)
            CaseLog.objects.create(
                case=case,
                event_type='asignacion',
                description=f'Caso asignado automáticamente al estudiante {selected_student.user.name}',
                executed_by=professor_user,
            )

            try:
                send_notification(
                    to=selected_student.user.email,
                    subject=f'Nuevo caso asignado — {case.id}',
                    body=(
                        f'Hola {selected_student.user.name},\n\n'
                        f'Se te ha asignado el caso #{case.id}.\n'
                        f'Beneficiario: {case.beneficiary.name if case.beneficiary else "No especificado"}\n'
                        f'Sala jurídica: {case.room.name}\n\n'
                        f'Ingresa al sistema para ver los detalles del caso.\n'
                    )
                )
            except Exception as e:
                CaseLog.objects.create(
                    case=case,
                    event_type='error_notificacion',
                    description=f'Error al enviar notificación de asignación: {e}',
                    executed_by=professor_user,
                )

    return assigned_cases
