# cases/scheduler.py
import logging
from django.utils import timezone
from datetime import timedelta

from notifications.services import send_notification

logger = logging.getLogger(__name__)


def get_appointments_due_for_reminder():
    """
    Retorna las citas que deben recibir recordatorio:
    - Dentro de las próximas 24 horas
    - reminder_sent = False
    - Status no cancelada ni completada
    """
    from cases.models import Appointment

    now    = timezone.now()
    window = now + timedelta(hours=24)

    return Appointment.objects.filter(
        scheduled_datetime__gte=now,
        scheduled_datetime__lte=window,
        reminder_sent=False,
    ).exclude(
        status__in=['cancelada', 'completada']
    ).select_related('case', 'case__beneficiary', 'case__room')


def send_appointment_reminders():
    """
    Job principal ejecutado por APScheduler cada hora.
    Itera las citas próximas y envía recordatorio al beneficiario.
    """
    appointments = get_appointments_due_for_reminder()
    logger.info(f"Scheduler: {appointments.count()} cita(s) próximas encontradas.")

    for appointment in appointments:
        _process_reminder(appointment)


def _process_reminder(appointment):
    """Procesa el recordatorio de una sola cita."""
    from cases.models import CaseLog
    from notifications.models import FailedNotification

    beneficiary = appointment.case.beneficiary
    case        = appointment.case

    # Validar que el beneficiario tenga correo
    if not beneficiary or not beneficiary.email or not beneficiary.email.strip():
        logger.warning(
            f"Cita {appointment.id} — beneficiario sin correo. Se omite envío."
        )
        # Registrar en bitácora
        CaseLog.objects.create(
            case=case,
            event_type='error_notificacion',
            description=(
                f"No se envió recordatorio de la cita {appointment.id}: "
                f"beneficiario sin correo registrado."
            ),
        )
        return

    # Construir contenido del correo
    subject, body = _build_reminder_email(appointment)

    # Validar que el contenido esté completo
    if not subject or not body:
        logger.error(f"Cita {appointment.id} — contenido del correo incompleto. Se omite envío.")
        return

    # Intentar envío
    try:
        send_notification(to=beneficiary.email, subject=subject, body=body)

        # Marcar como enviado para evitar duplicados
        appointment.reminder_sent = True
        appointment.save(update_fields=['reminder_sent'])

        # Registrar en bitácora del caso
        CaseLog.objects.create(
            case=case,
            event_type='notificacion_recordatorio',
            description=(
                f"Recordatorio de cita {appointment.id} enviado exitosamente "
                f"al beneficiario {beneficiary.email} "
                f"(Fecha/Hora: {appointment.scheduled_datetime.strftime('%d/%m/%Y %H:%M')})"
            ),
        )

        logger.info(f"Recordatorio enviado — Cita {appointment.id} → {beneficiary.email}")

    except Exception as e:
        logger.error(f"Error al enviar recordatorio — Cita {appointment.id}: {e}")
        # FailedNotification ya fue creado por send_notification
        # No modificar reminder_sent para permitir reintento en próxima ejecución


def _build_reminder_email(appointment):
    """Construye el asunto y cuerpo del correo de recordatorio."""
    try:
        case        = appointment.case
        beneficiary = case.beneficiary
        modality    = appointment.get_modality_display()
        fecha       = appointment.scheduled_datetime.strftime('%d/%m/%Y')
        hora        = appointment.scheduled_datetime.strftime('%H:%M')

        subject = f"Recordatorio de cita — Caso {case.id}"

        body = (
            f"Estimado/a {beneficiary.name},\n\n"
            f"Le recordamos que tiene una cita programada próximamente.\n\n"
            f"Detalles de su cita:\n"
            f"  • Caso ID:    {case.id}\n"
            f"  • Fecha:      {fecha}\n"
            f"  • Hora:       {hora}\n"
            f"  • Modalidad:  {modality}\n"
            f"  • Lugar/Enlace: {appointment.location_or_link or 'Por confirmar'}\n\n"
            f"Por favor, asegúrese de asistir puntualmente.\n"
            f"Si necesita reprogramar, comuníquese con la secretaría.\n\n"
            f"Este mensaje es generado automáticamente por el sistema BURO.\n"
        )

        return subject, body

    except Exception as e:
        logger.error(f"Error construyendo correo de recordatorio — Cita {appointment.id}: {e}")
        return None, None