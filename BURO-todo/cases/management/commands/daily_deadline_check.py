from django.core.management.base import BaseCommand
from django.utils import timezone
from cases.models import Case, CaseLog
from notifications.models import FailedNotification
from notifications.services import send_notification


class Command(BaseCommand):
    help = 'Check for cases with critical deadlines (≤ 3 days) and send email alerts to students'

    def handle(self, *args, **options):
        """
        Evaluación diaria automatizada de vencimientos críticos.
        Envía alertas por correo a estudiantes con casos que vencen en ≤ 3 días.
        """
        today = timezone.now().date()
        critical_deadline = today + timezone.timedelta(days=3)

        # Obtener casos activos que vencen en ≤ 3 días
        critical_cases = Case.objects.filter(
            status='active',
            legal_deadline__lte=critical_deadline
        ).select_related('student__user', 'beneficiary', 'room')

        self.stdout.write(f'Encontrados {critical_cases.count()} casos críticos para evaluación')

        for case in critical_cases:
            days_remaining = (case.legal_deadline - today).days
            
            # Verificar que el estudiante tenga email
            if not case.student or not case.student.user.email:
                self.stdout.write(
                    self.style.WARNING(
                        f'Caso {case.number}: estudiante sin email registrado, omitiendo'
                    )
                )
                continue

            student_email = case.student.user.email
            subject = f'URGENTE — Caso {case.number} vence en {days_remaining} día(s)'
            
            message = f"""
Estimado/a {case.student.user.name},

Le informamos que el caso asignado está próximo a vencer:

- Número de caso: {case.number}
- Beneficiario: {case.beneficiary.name if case.beneficiary else 'N/A'}
- Sala jurídica: {case.room.name}
- Días restantes para vencimiento legal: {days_remaining}

Acción requerida:
- Revise inmediatamente el estado del caso
- Complete todas las acciones académicas pendientes
- Contacte a su profesor asesor si necesita asistencia
- Asegúrese de que toda la documentación esté completa

Esta es una alerta automática del sistema BURO. No responda a este correo.

Atentamente,
Sistema BURO - Universidad Icesi
"""

            try:
                # Enviar notificación
                send_notification(
                    to=student_email,
                    subject=subject,
                    body=message.strip()
                )

                # Registrar en bitácora
                CaseLog.objects.create(
                    case=case,
                    event_type='deadline_alert',
                    description=f'Alerta de vencimiento enviada al estudiante. Días restantes: {days_remaining}',
                    executed_by=None,  # Sistema automatizado
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Correo enviado exitosamente para caso {case.number}'
                    )
                )

            except Exception as e:
                # Registrar error en bitácora
                CaseLog.objects.create(
                    case=case,
                    event_type='deadline_alert_error',
                    description=f'Error al enviar alerta de vencimiento: {str(e)}',
                    executed_by=None,
                )

                # Crear alerta interna para coordinador
                FailedNotification.objects.create(
                    to=student_email,
                    subject=subject,
                    body=message.strip(),
                    error_message=str(e),
                )

                self.stdout.write(
                    self.style.ERROR(
                        f'Error enviando correo para caso {case.number}: {str(e)}'
                    )
                )

        self.stdout.write(self.style.SUCCESS('Evaluación diaria completada'))