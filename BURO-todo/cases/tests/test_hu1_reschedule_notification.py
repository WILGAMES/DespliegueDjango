# cases/tests/test_hu1_reschedule_notification.py
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta

from cases.models import Appointment, AppointmentLog, Case
from accounts.models import SystemUser, Role, LegalRoom, Student, Professor, Beneficiary


class HU1BaseSetup(TestCase):
    """Datos base para todos los tests de HU1."""

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Laboral')

        self.prof_role = Role.objects.create(name='profesor')
        self.sec_role  = Role.objects.create(name='secretaria')
        self.stu_role  = Role.objects.create(name='estudiante')

        # Profesor
        self.prof_user = SystemUser.objects.create_user(
            email='prof@icesi.edu.co', password='test123',
            name='Carlos Profesor', role=self.prof_role, room=self.room
        )
        self.professor = Professor.objects.create(user=self.prof_user)

        # Secretaria
        self.sec_user = SystemUser.objects.create_user(
            email='sec@icesi.edu.co', password='test123',
            name='Ana Secretaria', role=self.sec_role
        )

        # Estudiante
        self.stu_user = SystemUser.objects.create_user(
            email='stu@icesi.edu.co', password='test123',
            name='Luis Estudiante', role=self.stu_role, room=self.room
        )
        self.student = Student.objects.create(
            user=self.stu_user, semester=5, student_code='A00123'
        )

        # Beneficiario
        self.beneficiary = Beneficiary.objects.create_user(
            document='999888', email='ben@gmail.com', password='test123',
            name='Pedro Beneficiario', phone='3001234567',
            address='Calle 5', stratum=2
        )

        # Caso
        self.case = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timedelta(days=60),
            beneficiary=self.beneficiary,
            student=self.student,
        )

        # Cita base
        self.original_dt = timezone.now() + timedelta(days=5)
        self.appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=self.original_dt,
            modality='presencial',
            location_or_link='Sala 301',
            created_by=self.sec_user,
        )

        self.client = Client()


# ─── Tests del signal ────────────────────────────────────────────────────────

class AppointmentRescheduleSignalTest(HU1BaseSetup):
    """Verifica que el signal detecta reprogramaciones y ejecuta la lógica."""

    @patch('cases.signals.send_notification')
    def test_signal_creates_appointment_log_on_reschedule(self, mock_send):
        """Al guardar una nueva fecha, se crea un AppointmentLog."""
        new_dt = self.original_dt + timedelta(days=7)
        self.appointment._reschedule_reason = 'Solicitud del cliente'
        self.appointment._changed_by = self.sec_user
        self.appointment.scheduled_datetime = new_dt
        self.appointment.save()

        log = AppointmentLog.objects.filter(appointment=self.appointment).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.previous_datetime, self.original_dt)
        self.assertEqual(log.new_datetime, new_dt)
        self.assertFalse(log.no_reason_flag)

    @patch('cases.signals.send_notification')
    def test_signal_sends_email_to_professor_on_reschedule(self, mock_send):
        """El signal envía correo al profesor con los datos correctos."""
        new_dt = self.original_dt + timedelta(days=7)
        self.appointment._reschedule_reason = 'Audiencia cancelada'
        self.appointment._changed_by = self.sec_user
        self.appointment.scheduled_datetime = new_dt
        self.appointment.save()

        mock_send.assert_called()
        call_kwargs = mock_send.call_args
        # Verifica asunto correcto
        subject = call_kwargs[1]['subject'] if call_kwargs[1] else call_kwargs[0][1]
        self.assertIn(str(self.case.id), subject)
        self.assertIn(self.room.name, subject)

    @patch('cases.signals.send_notification')
    def test_signal_sets_no_reason_flag_when_reason_empty(self, mock_send):
        """Si el motivo está vacío, no_reason_flag=True en el log."""
        new_dt = self.original_dt + timedelta(days=3)
        self.appointment._reschedule_reason = ''
        self.appointment._changed_by = self.stu_user
        self.appointment.scheduled_datetime = new_dt
        self.appointment.save()

        log = AppointmentLog.objects.filter(appointment=self.appointment).first()
        self.assertTrue(log.no_reason_flag)

    @patch('cases.signals.send_notification')
    def test_signal_sends_extra_alert_when_no_reason(self, mock_send):
        """Si no hay motivo, se envían DOS correos al profesor."""
        new_dt = self.original_dt + timedelta(days=3)
        self.appointment._reschedule_reason = ''
        self.appointment._changed_by = self.stu_user
        self.appointment.scheduled_datetime = new_dt
        self.appointment.save()

        # Debe haber exactamente 2 llamadas: correo normal + alerta
        self.assertEqual(mock_send.call_count, 2)

    @patch('cases.signals.send_notification')
    def test_signal_does_not_fire_on_new_appointment(self, mock_send):
        """El signal NO envía correo al crear una cita nueva."""
        Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(days=10),
            modality='virtual',
            location_or_link='https://meet.google.com/abc',
            created_by=self.sec_user,
        )
        mock_send.assert_not_called()

    @patch('cases.signals.send_notification')
    def test_appointment_status_changes_to_reprogramada(self, mock_send):
        """El status de la cita cambia a 'reprogramada' tras el cambio."""
        new_dt = self.original_dt + timedelta(days=7)
        self.appointment._reschedule_reason = 'Motivo válido'
        self.appointment._changed_by = self.sec_user
        self.appointment.scheduled_datetime = new_dt
        self.appointment.save()

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'reprogramada')


# ─── Tests de la view de reprogramación ──────────────────────────────────────

class RescheduleViewTest(HU1BaseSetup):
    """Verifica el endpoint POST de reprogramación de citas."""

    def test_secretaria_can_reschedule(self):
        """La secretaria puede reprogramar una cita con motivo."""
        self.client.login(email='sec@icesi.edu.co', password='test123')
        new_dt = (self.original_dt + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')

        with patch('cases.signals.send_notification'):
            response = self.client.post(
                reverse('cases:reschedule_appointment', args=[self.appointment.id]),
                {'new_datetime': new_dt, 'reason': 'Solicitud del cliente'},
            )

        self.assertIn(response.status_code, [200, 302])
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'reprogramada')

    def test_reschedule_without_reason_sets_flag(self):
        """Reprogramar sin motivo activa no_reason_flag en el log."""
        self.client.login(email='sec@icesi.edu.co', password='test123')
        new_dt = (self.original_dt + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M')

        with patch('cases.signals.send_notification'):
            self.client.post(
                reverse('cases:reschedule_appointment', args=[self.appointment.id]),
                {'new_datetime': new_dt, 'reason': ''},
            )

        log = AppointmentLog.objects.filter(appointment=self.appointment).first()
        self.assertIsNotNone(log)
        self.assertTrue(log.no_reason_flag)

    def test_unauthenticated_user_cannot_reschedule(self):
        """Un usuario no autenticado es redirigido al login."""
        new_dt = (self.original_dt + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(
            reverse('cases:reschedule_appointment', args=[self.appointment.id]),
            {'new_datetime': new_dt, 'reason': 'Test'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


# ─── Tests de la vista de historial (solo lectura) ───────────────────────────

class AppointmentHistoryViewTest(HU1BaseSetup):
    """Verifica la vista de historial de reprogramaciones del profesor."""

    def setUp(self):
        super().setUp()
        # Crea algunos logs de ejemplo
        new_dt = self.original_dt + timedelta(days=3)
        AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.sec_user,
            previous_datetime=self.original_dt,
            new_datetime=new_dt,
            reason='Cambio de agenda',
            no_reason_flag=False,
        )
        AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.stu_user,
            previous_datetime=new_dt,
            new_datetime=new_dt + timedelta(days=2),
            reason='',
            no_reason_flag=True,
        )

    def test_professor_can_view_history(self):
        """El profesor puede ver el historial de reprogramaciones."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:appointment_history', args=[self.appointment.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('logs', response.context)
        self.assertEqual(len(response.context['logs']), 2)

    def test_history_shows_sin_motivo_when_flag_true(self):
        """El historial muestra 'Sin motivo registrado' cuando no_reason_flag=True."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:appointment_history', args=[self.appointment.id])
        )
        self.assertContains(response, 'Sin motivo registrado')

    def test_history_is_read_only_no_edit_forms(self):
        """La vista del historial no contiene formularios de edición."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:appointment_history', args=[self.appointment.id])
        )
        # No debe haber inputs de tipo text ni formularios de edición
        self.assertNotContains(response, '<input type="text"')
        self.assertNotContains(response, 'method="post"')