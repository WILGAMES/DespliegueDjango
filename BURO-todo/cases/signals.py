# cases/signals.py
import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

from notifications.services import send_notification

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='cases.Appointment')
def capture_previous_datetime(sender, instance, **kwargs):
    """
    Antes de guardar, captura la fecha anterior desde la BD
    para poder compararla después en post_save.
    """
    if not instance.pk:
        # Cita nueva — no hay nada que capturar
        instance._previous_datetime = None
        return

    try:
        from cases.models import Appointment
        original = Appointment.objects.get(pk=instance.pk)
        instance._previous_datetime = original.scheduled_datetime
    except Exception:
        instance._previous_datetime = None


@receiver(post_save, sender='cases.Appointment')
def handle_appointment_reschedule(sender, instance, created, **kwargs):
    """
    Después de guardar, si la fecha cambió:
    - Crea un AppointmentLog con todos los datos
    - Envía correo al profesor
    - Si no hay motivo, envía alerta adicional
    - Actualiza status a 'reprogramada'
    """
    if created:
        # Cita recién creada — no es reprogramación
        return

    previous_dt = getattr(instance, '_previous_datetime', None)
    if previous_dt is None or previous_dt == instance.scheduled_datetime:
        # La fecha no cambió — no es reprogramación
        return

    reason     = getattr(instance, '_reschedule_reason', '')
    changed_by = getattr(instance, '_changed_by', None)
    no_reason  = not reason or not reason.strip()

    # 1. Crear AppointmentLog
    _create_appointment_log(instance, previous_dt, reason, changed_by, no_reason)

    # 2. Actualizar status a 'reprogramada' (sin disparar el signal de nuevo)
    from cases.models import Appointment
    Appointment.objects.filter(pk=instance.pk).update(status='reprogramada')
    instance.status = 'reprogramada'

    # 3. Enviar correo principal al profesor
    _send_reschedule_email(instance, previous_dt, changed_by, reason)

    # 4. Si no hay motivo y el cambio lo hizo un estudiante, alerta adicional
    if no_reason:
        _send_no_reason_alert(instance, changed_by)


def _create_appointment_log(appointment, previous_dt, reason, changed_by, no_reason):
    """Registra el cambio en la bitácora de la cita."""
    from cases.models import AppointmentLog
    try:
        AppointmentLog.objects.create(
            appointment=appointment,
            changed_by=changed_by,
            previous_datetime=previous_dt,
            new_datetime=appointment.scheduled_datetime,
            reason=reason or '',
            no_reason_flag=no_reason,
        )
    except Exception as e:
        logger.error(f"Error al crear AppointmentLog para cita {appointment.pk}: {e}")


def _send_reschedule_email(appointment, previous_dt, changed_by, reason):
    """Construye y envía el correo principal al profesor de la sala."""
    try:
        professor_email = appointment.case.professor.user.email
        case_id         = appointment.case.id
        room_name       = appointment.case.room.name
        student_name    = (
            appointment.case.student.user.name
            if appointment.case.student else 'Sin asignar'
        )
        actor_name = changed_by.name if changed_by else 'Sistema'

        subject = f"Cita reprogramada — Caso {case_id} ({room_name})"

        body = (
            f"Estimado/a {appointment.case.professor.user.name},\n\n"
            f"Se ha reprogramado una cita asociada a un caso de su sala.\n\n"
            f"Detalles del cambio:\n"
            f"  • Caso ID:           {case_id}\n"
            f"  • Sala:              {room_name}\n"
            f"  • Estudiante:        {student_name}\n"
            f"  • Fecha anterior:    {previous_dt.strftime('%d/%m/%Y %H:%M')}\n"
            f"  • Nueva fecha:       {appointment.scheduled_datetime.strftime('%d/%m/%Y %H:%M')}\n"
            f"  • Cambio realizado por: {actor_name}\n"
            f"  • Motivo:            {reason if reason else 'Sin motivo registrado'}\n\n"
            f"Este mensaje es generado automáticamente por el sistema BURO.\n"
        )

        send_notification(to=professor_email, subject=subject, body=body)

    except Exception as e:
        logger.error(f"Error al enviar correo de reprogramación al profesor — Cita {appointment.pk}: {e}")


def _send_no_reason_alert(appointment, changed_by):
    """Envía alerta adicional al profesor cuando no hay motivo documentado."""
    try:
        professor_email = appointment.case.professor.user.email
        case_id         = appointment.case.id
        student_name    = (
            appointment.case.student.user.name
            if appointment.case.student else 'Sin asignar'
        )
        actor_name = changed_by.name if changed_by else 'Usuario desconocido'

        subject = f"⚠ Alerta — Reprogramación sin motivo — Caso {case_id}"

        body = (
            f"Estimado/a {appointment.case.professor.user.name},\n\n"
            f"⚠ ALERTA DE AUDITORÍA\n\n"
            f"El usuario {actor_name} reprogramó la cita del caso {case_id} "
            f"sin registrar un motivo.\n\n"
            f"  • Estudiante asignado: {student_name}\n"
            f"  • Nueva fecha:         {appointment.scheduled_datetime.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"Este evento ha quedado marcado en la bitácora con flag 'sin_motivo: true' "
            f"para facilitar su auditoría.\n\n"
            f"Este mensaje es generado automáticamente por el sistema BURO.\n"
        )

        send_notification(to=professor_email, subject=subject, body=body)

    except Exception as e:
        logger.error(f"Error al enviar alerta sin motivo al profesor — Cita {appointment.pk}: {e}")


@receiver(pre_save, sender='cases.Case')
def capture_previous_case_status(sender, instance, **kwargs):
    """Captura el estado anterior del caso antes de guardar para detectar cambios."""
    if not instance.pk:
        instance._previous_status = None
        return

    try:
        from cases.models import Case
        original = Case.objects.get(pk=instance.pk)
        instance._previous_status = original.status
    except Exception:
        instance._previous_status = None


@receiver(post_save, sender='cases.Case')
def handle_pending_case_assignment(sender, instance, created, **kwargs):
    """Si el caso queda en estado Pendiente, intenta asignarlo automáticamente."""
    if instance.status != 'Pendiente':
        return

    if instance.student or instance.assigned_student:
        logger.debug(
            f"Caso {instance.pk} ya tiene estudiante asignado; se omite la asignación automática."
        )
        return

    previous_status = getattr(instance, '_previous_status', None)
    if not created and previous_status == 'Pendiente':
        return

    try:
        from cases.models import CaseLog
        from cases.services.student_assignment_service import assign_case_to_student

        selected_student = assign_case_to_student(instance)
        if selected_student is None:
            CaseLog.objects.create(
                case=instance,
                event_type='error_notificacion',
                description='No se asignó el caso automáticamente: no hay estudiantes elegibles.',
                executed_by=None,
            )
            return

        CaseLog.objects.create(
            case=instance,
            event_type='asignacion',
            description=(
                f'Caso asignado automáticamente al estudiante '
                f'{selected_student.user.email} ({selected_student.user.name}).'
            ),
            executed_by=None,
        )

    except Exception as exc:
        logger.exception(f"Error al asignar automáticamente el caso {instance.pk}: {exc}")
        try:
            from cases.models import CaseLog

            CaseLog.objects.create(
                case=instance,
                event_type='error_notificacion',
                description=(
                    f'Error al asignar automáticamente el caso: {str(exc)}'
                ),
                executed_by=None,
            )
        except Exception as log_exc:
            logger.error(
                f"Error al registrar el log de asignación automática para caso {instance.pk}: {log_exc}"
            )
