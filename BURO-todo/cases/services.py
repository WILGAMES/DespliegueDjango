from django.core.exceptions import ValidationError
from django.db.models import Avg
from cases.models import AcademicAction, GradeWeightConfig, Case


def filter_cases_by_status(status):
    """
    Filter cases by status with ordering by most recent.
    - If status == "activos": return cases where status != "Cerrado"
    - If status == "cerrados": return cases where status == "Cerrado"
    - Ordered by created_at descending (most recent first)
    """
    if status == "activos":
        return Case.objects.exclude(status="Cerrado").order_by('-created_at')
    elif status == "cerrados":
        return Case.objects.filter(status="Cerrado").order_by('-created_at')
    else:
        # Invalid status, return empty queryset
        return Case.objects.none()


def calculate_final_grade(student, period, room):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 2: calcula la nota final ponderada del estudiante para un
    período y sala específicos usando la configuración de pesos activa.

    Fórmula:
        nota_final = (promedio_documents * weight_documents / 100)
                   + (promedio_followups * weight_followups / 100)
                   + (promedio_attendance * weight_attendance / 100)

    Si el estudiante no tiene acciones de algún tipo, ese componente = 0.0
    Resultado redondeado a 1 decimal dentro del rango 0.0 - 5.0
    """

    # Buscar configuración de pesos activa para el profesor/sala/período
    # Si no existe, el cálculo no puede ejecutarse — criterio 6
    try:
        config = GradeWeightConfig.objects.get(
            professor=student.assigned_cases.filter(room=room).first().professor,
            room=room,
            period=period,
        )
    except GradeWeightConfig.DoesNotExist:
        raise ValidationError('No hay configuración de evaluación activa para este período')

    # Obtener todas las acciones académicas del estudiante en esa sala y período
    # filtrando por los casos del estudiante en esa sala
    actions = AcademicAction.objects.filter(
        case__student=student,
        case__room=room,
    )

    # Calcular promedio por tipo — convertir a float para evitar conflictos con Decimal
    avg_documents  = float(actions.filter(action_type='document').aggregate(
        avg=Avg('grade'))['avg'] or 0.0)

    avg_followups  = float(actions.filter(action_type='followup').aggregate(
        avg=Avg('grade'))['avg'] or 0.0)

    avg_attendance = float(actions.filter(action_type='attendance').aggregate(
        avg=Avg('grade'))['avg'] or 0.0)

    # Aplicar pesos de la configuración activa
    final_grade = (
        (avg_documents  * config.weight_documents  / 100) +
        (avg_followups  * config.weight_followups  / 100) +
        (avg_attendance * config.weight_attendance / 100)
    )

    # Redondear a 1 decimal y retornar como float — criterio 2
    return round(float(final_grade), 1)


# ============================================================
# PTCJMGA-XX: Sanciones Academicas (Reasignacion como sancion)
# ============================================================

from django.core.exceptions import PermissionDenied
from django.db import transaction
from cases.models import CaseLog


# Roles autorizados para aplicar sanciones
ROLES_AUTORIZADOS_SANCION = ['professor', 'profesor', 'admin', 'coordinator', 'coordinador']


class SanctionService:
    """
    PTCJMGA-XX: Servicio para aplicar sanciones academicas sobre casos.

    Implementa la logica de negocio para que un profesor reasigne un caso
    a un estudiante como sancion academica, con trazabilidad inmutable
    en CaseLog (event_type='sancion').

    Uso:
        SanctionService.apply_sanction(
            case=case_obj,
            sanctioned_student=student_obj,
            applied_by=request.user,
            reason='El estudiante no realizo la entrevista inicial correctamente',
        )
    """

    @staticmethod
    @transaction.atomic
    def apply_sanction(case, sanctioned_student, applied_by, reason):
        """
        Aplica una sancion academica reasignando el caso al estudiante sancionado.


        Args:
            case: instancia de Case a reasignar
            sanctioned_student: instancia de Student que recibira la sancion
            applied_by: instancia de SystemUser que aplica la sancion (profesor)
            reason: motivo de la sancion (obligatorio)

        Returns:
            CaseLog: el registro de sancion creado

        Raises:
            PermissionDenied: si applied_by no tiene rol autorizado
            ValidationError: si el motivo esta vacio
        """
        # 1. Validar permisos
        SanctionService._validate_permission(applied_by)

        # 2. Validar motivo
        if not reason or not reason.strip():
            raise ValidationError('El motivo de la sancion es obligatorio.')

        clean_reason = reason.strip()

        # 3. Construir descripcion para la bitacora
        previous_student_name = (
            case.student.user.name if case.student else '(sin asignar)'
        )
        description = (
            f'SANCION ACADEMICA aplicada por {applied_by.name}. '
            f'Caso reasignado de {previous_student_name} a {sanctioned_student.user.name}. '
            f'Motivo: {clean_reason}'
        )

        # 4. Reasignar el caso al estudiante sancionado
        case.student = sanctioned_student
        if hasattr(case, 'assigned_student'):
            case.assigned_student = sanctioned_student.user
        case.save()

        # 5. Crear registro inmutable en bitacora
        log = CaseLog.objects.create(
            case=case,
            event_type='sancion',
            description=description,
            executed_by=applied_by,
        )

        return log

    @staticmethod
    def _validate_permission(user):
        """
        Valida que el usuario tenga rol autorizado para aplicar sanciones.
        Solo profesor, coordinador, admin, superuser o staff.

        Raises:
            PermissionDenied: si el usuario no tiene permiso
        """
        # Superuser o staff siempre pueden
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
        """
        Retorna queryset de sanciones aplicadas a un estudiante (Escenario 3 Gherkin).

        Args:
            student: instancia de Student

        Returns:
            QuerySet de CaseLog con event_type='sancion' donde el estudiante actual
            del caso es el sancionado, ordenadas por fecha descendente.
        """
        return CaseLog.objects.filter(
            event_type='sancion',
            case__student=student,
        ).select_related('case', 'executed_by').order_by('-created_at')