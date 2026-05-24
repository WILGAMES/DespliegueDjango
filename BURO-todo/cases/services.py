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