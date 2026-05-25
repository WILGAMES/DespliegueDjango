from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Avg
from cases.models import AcademicAction, GradeWeightConfig, Case, CaseLog


def filter_cases_by_status(status):
    if status == "activos":
        return Case.objects.exclude(status="Cerrado").order_by('-created_at')
    elif status == "cerrados":
        return Case.objects.filter(status="Cerrado").order_by('-created_at')
    else:
        return Case.objects.none()


def calculate_final_grade(student, period, room):
    try:
        config = GradeWeightConfig.objects.get(
            professor=student.assigned_cases.filter(room=room).first().professor,
            room=room,
            period=period,
        )
    except GradeWeightConfig.DoesNotExist:
        raise ValidationError('No hay configuración de evaluación activa para este período')

    actions = AcademicAction.objects.filter(
        case__student=student,
        case__room=room,
    )

    avg_documents  = float(actions.filter(action_type='document').aggregate(avg=Avg('grade'))['avg'] or 0.0)
    avg_followups  = float(actions.filter(action_type='followup').aggregate(avg=Avg('grade'))['avg'] or 0.0)
    avg_attendance = float(actions.filter(action_type='attendance').aggregate(avg=Avg('grade'))['avg'] or 0.0)

    final_grade = (
        (avg_documents  * config.weight_documents  / 100) +
        (avg_followups  * config.weight_followups  / 100) +
        (avg_attendance * config.weight_attendance / 100)
    )

    return round(float(final_grade), 1)


ROLES_AUTORIZADOS_SANCION = ['professor', 'profesor', 'admin', 'coordinator', 'coordinador']


class SanctionService:

    @staticmethod
    @transaction.atomic
    def apply_sanction(case, sanctioned_student, applied_by, reason):
        SanctionService._validate_permission(applied_by)

        if not reason or not reason.strip():
            raise ValidationError('El motivo de la sancion es obligatorio.')

        clean_reason = reason.strip()

        previous_student_name = (
            case.student.user.name if case.student else '(sin asignar)'
        )
        description = (
            f'SANCION ACADEMICA aplicada por {applied_by.name}. '
            f'Caso reasignado de {previous_student_name} a {sanctioned_student.user.name}. '
            f'Motivo: {clean_reason}'
        )

        case.student = sanctioned_student
        if hasattr(case, 'assigned_student'):
            case.assigned_student = sanctioned_student.user
        case.save()

        log = CaseLog.objects.create(
            case=case,
            event_type='sancion',
            description=description,
            executed_by=applied_by,
        )

        return log

    @staticmethod
    def _validate_permission(user):
        if user.is_superuser or user.is_staff:
            return True

        user_role = getattr(user, 'role', None)
        if not user_role:
            raise PermissionDenied(
                'No tiene permisos para aplicar sanciones academicas. '
                'Su usuario no tiene un rol asignado.'
            )

        role_name = user_role.name.lower()
        if role_name not in ROLES_AUTORIZADOS_SANCION:
            raise PermissionDenied(
                'No tiene permisos para aplicar sanciones academicas. '
                'Esta funcion es exclusiva de profesores y coordinadores.'
            )

        return True

    @staticmethod
    def get_student_sanctions(student):
        return CaseLog.objects.filter(
            event_type='sancion',
            case__student=student,
        ).select_related('case', 'executed_by').order_by('-created_at')
