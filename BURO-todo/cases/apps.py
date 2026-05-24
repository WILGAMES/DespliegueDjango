# cases/apps.py
from django.apps import AppConfig


class CasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cases'

    def ready(self):
        import cases.signals  # noqa: F401 — conecta los signals al arrancar
        self._setup_scheduler()

    def _setup_scheduler(self):
        """Configura APScheduler para ejecutar tareas automáticas."""
        from apscheduler.schedulers.background import BackgroundScheduler
        from django.conf import settings
        import logging

        logger = logging.getLogger(__name__)

        # Evitar crear múltiples instancias del scheduler
        if hasattr(self, '_scheduler_running'):
            return

        try:
            scheduler = BackgroundScheduler()
            
            # Agregar el job de envío de recordatorios cada hora
            from cases.scheduler import send_appointment_reminders
            scheduler.add_job(
                send_appointment_reminders,
                'interval',
                hours=1,
                id='send_appointment_reminders',
                name='Envío de recordatorios automáticos de citas',
                replace_existing=True,
            )

            scheduler.start()
            self._scheduler_running = True
            logger.info("APScheduler inicializado: Job 'send_appointment_reminders' ejecutándose cada hora")

        except Exception as e:
            logger.error(f"Error al inicializar APScheduler: {e}")
            self._scheduler_running = False