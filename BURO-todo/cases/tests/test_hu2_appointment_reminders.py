# cases/tests/test_hu2_appointment_reminders.py
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, call
from datetime import timedelta

from cases.models import Appointment, Case
from accounts.models import SystemUser, Role, LegalRoom, Student, Professor, Beneficiary
from notifications.models import FailedNotification


class HU2BaseSetup(TestCase):
    """Datos base para todos los tests de HU2."""

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Penal')

        self.prof_role = Role.objects.create(name='profesor')
        self.sec_role  = Role.objects.create(name='secretaria')

        self.prof_user = SystemUser.objects.create_user(
            email='prof@icesi.edu.co', password='test123',
            name='Carlos Profesor', role=self.prof_role, room=self.room
        )
        self.professor = Professor.objects.create(user=self.prof_user)

        self.sec_user = SystemUser.objects.create_user(
            email='sec@icesi.edu.co', password='test123',
            name='Ana Secretaria', role=self.sec_role
        )

        # Beneficiario CON correo
        self.beneficiary = Beneficiary.objects.create_user(
            document='111222', email='ben@gmail.com', password='test123',
            name='Pedro Beneficiario', phone='3001234567',
            address='Calle 1', stratum=2
        )

        # Beneficiario SIN correo
        self.beneficiary_no_email = Beneficiary.objects.create_user(
            document='333444', email='noemail@placeholder.com', password='test123',
            name='Sin Correo Beneficiario', phone='3009999999',
            address='Calle 2', stratum=1
        )
        # Simulamos que no tiene correo útil
        self.beneficiary_no_email.email = ''
        self.beneficiary_no_email.save()

        self.case = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timedelta(days=60),
            beneficiary=self.beneficiary,
        )

        self.case_no_email = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timedelta(days=60),
            beneficiary=self.beneficiary_no_email,
        )


class ReminderFilterTest(HU2BaseSetup):
    """Verifica que el job filtra correctamente las citas dentro de 24 horas."""

    def test_appointment_within_24h_is_selected(self):
        """Una cita en 20 horas debe ser seleccionada para recordatorio."""
        from cases.scheduler import get_appointments_due_for_reminder

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        due = get_appointments_due_for_reminder()
        self.assertIn(appointment, due)

    def test_appointment_outside_24h_is_not_selected(self):
        """Una cita en 48 horas NO debe ser seleccionada."""
        from cases.scheduler import get_appointments_due_for_reminder

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=48),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        due = get_appointments_due_for_reminder()
        self.assertNotIn(appointment, due)

    def test_appointment_already_reminded_is_excluded(self):
        """Una cita con reminder_sent=True NO debe seleccionarse de nuevo."""
        from cases.scheduler import get_appointments_due_for_reminder

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='virtual',
            location_or_link='https://meet.google.com/abc',
            created_by=self.sec_user,
            reminder_sent=True,  # ya se envió
        )

        due = get_appointments_due_for_reminder()
        self.assertNotIn(appointment, due)

    def test_cancelled_appointment_is_excluded(self):
        """Una cita cancelada no debe recibir recordatorio."""
        from cases.scheduler import get_appointments_due_for_reminder

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
            status='cancelada',
        )

        due = get_appointments_due_for_reminder()
        self.assertNotIn(appointment, due)


class ReminderEmailTest(HU2BaseSetup):
    """Verifica el contenido y envío del correo de recordatorio."""

    @patch('cases.scheduler.send_notification')
    def test_reminder_email_sent_to_beneficiary(self, mock_send):
        """Se envía correo al beneficiario con los datos correctos."""
        from cases.scheduler import send_appointment_reminders

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[1]['to'], self.beneficiary.email)
        self.assertIn(str(self.case.id), call_args[1]['subject'])

    @patch('cases.scheduler.send_notification')
    def test_reminder_sent_flag_set_after_sending(self, mock_send):
        """Después del envío, reminder_sent=True para evitar duplicados."""
        from cases.scheduler import send_appointment_reminders

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='virtual',
            location_or_link='https://meet.google.com/xyz',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        appointment.refresh_from_db()
        self.assertTrue(appointment.reminder_sent)

    @patch('cases.scheduler.send_notification')
    def test_no_duplicate_reminders(self, mock_send):
        """Ejecutar el job dos veces no envía dos correos."""
        from cases.scheduler import send_appointment_reminders

        Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        send_appointment_reminders()
        send_appointment_reminders()

        self.assertEqual(mock_send.call_count, 1)

    @patch('cases.scheduler.send_notification')
    def test_bitacora_logged_on_successful_send(self, mock_send):
        """Se registra en bitácora cuando el envío es exitoso."""
        from cases.scheduler import send_appointment_reminders
        from cases.models import CaseLog

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        log = CaseLog.objects.filter(case=self.case).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, 'notificacion_recordatorio')
        self.assertIn(str(appointment.id), log.description)
        self.assertIn(self.beneficiary.email, log.description)


class ReminderNoBeneficiaryEmailTest(HU2BaseSetup):
    """Verifica el manejo de beneficiarios sin correo."""

    @patch('cases.scheduler.send_notification')
    def test_no_email_sent_when_beneficiary_has_no_email(self, mock_send):
        """No se envía correo si el beneficiario no tiene email."""
        from cases.scheduler import send_appointment_reminders

        Appointment.objects.create(
            case=self.case_no_email,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 202',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        mock_send.assert_not_called()

    @patch('cases.scheduler.send_notification')
    def test_bitacora_logged_when_no_email(self, mock_send):
        """Se registra en bitácora cuando no hay correo del beneficiario."""
        from cases.scheduler import send_appointment_reminders
        from cases.models import CaseLog

        Appointment.objects.create(
            case=self.case_no_email,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 202',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        log = CaseLog.objects.filter(case=self.case_no_email).first()
        self.assertIsNotNone(log)
        self.assertIn('sin correo', log.description.lower())


class ReminderErrorHandlingTest(HU2BaseSetup):
    """Verifica el manejo de errores en el envío."""

    @patch('cases.scheduler.send_notification', side_effect=Exception('SMTP error'))
    def test_failed_notification_created_on_send_error(self, mock_send):
        """Si el envío falla, se crea un FailedNotification."""
        from cases.scheduler import send_appointment_reminders

        Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        self.assertTrue(FailedNotification.objects.exists())

    @patch('cases.scheduler.send_notification', side_effect=Exception('SMTP error'))
    def test_appointment_not_modified_on_send_error(self, mock_send):
        """Si el envío falla, reminder_sent sigue en False."""
        from cases.scheduler import send_appointment_reminders

        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.sec_user,
        )

        send_appointment_reminders()

        appointment.refresh_from_db()
        self.assertFalse(appointment.reminder_sent)