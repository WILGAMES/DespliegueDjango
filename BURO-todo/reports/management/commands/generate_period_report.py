from datetime import date
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Genera el reporte académico de un periodo y notifica a los coordinadores. '
        'Usar al cierre de cada periodo académico (HU: Reportes automáticos por periodo).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--period', required=True, help='Etiqueta del periodo (ej. 2026-1)')
        parser.add_argument('--date-from', required=True, help='Fecha de inicio YYYY-MM-DD')
        parser.add_argument('--date-to', required=True, help='Fecha de cierre YYYY-MM-DD')

    def handle(self, *args, **options):
        from reports.services import generate_and_save_report
        from accounts.models import SystemUser
        from notifications.services import send_notification

        period_label = options['period']

        try:
            date_from = date.fromisoformat(options['date_from'])
            date_to = date.fromisoformat(options['date_to'])
        except ValueError as exc:
            raise CommandError(f'Formato de fecha inválido: {exc}')

        self.stdout.write(
            f'Generando reporte para {period_label} ({date_from} → {date_to})...'
        )

        try:
            report = generate_and_save_report(
                period_label=period_label,
                date_from=date_from,
                date_to=date_to,
                is_automatic=True,
            )
        except Exception as exc:
            # HU2 criterio: no almacenar reporte incompleto — el error se propaga
            # antes de que se cree el objeto, así que no hay que borrar nada
            logger.error('Fallo al generar reporte automático %s: %s', period_label, exc)
            self.stdout.write(self.style.ERROR(f'Error al generar reporte: {exc}'))
            self.stdout.write(
                self.style.ERROR('El error fue registrado. No se almacenó ningún reporte incompleto.')
            )
            return

        self.stdout.write(self.style.SUCCESS(f'Reporte #{report.pk} generado correctamente.'))

        # Notificar a todos los coordinadores (is_staff o rol secretaria)
        coordinators = SystemUser.objects.filter(
            Q(is_staff=True) | Q(role__name__icontains='secretaria')
        ).values_list('email', flat=True).distinct()

        notified = 0
        for email in filter(None, coordinators):
            try:
                send_notification(
                    to=email,
                    subject=f'Reporte académico disponible — {period_label}',
                    body=(
                        f'El reporte académico del periodo {period_label} ha sido generado automáticamente.\n\n'
                        f'Periodo cubierto: {date_from} al {date_to}\n'
                        f'Casos incluidos: {report.report_data.get("summary", {}).get("total_cases", 0)}\n\n'
                        f'Ingrese al sistema para visualizarlo o descargarlo en /reports/\n\n'
                        f'Este es un mensaje automático del sistema BURO. No responda a este correo.'
                    ),
                )
                notified += 1
                self.stdout.write(self.style.SUCCESS(f'Notificación enviada a {email}'))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'Error al notificar a {email}: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(f'Proceso completado. Notificados: {notified} coordinador(es).')
        )
