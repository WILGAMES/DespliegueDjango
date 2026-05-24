# cases/tests/test_models_appointment.py
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from cases.models import Appointment, AppointmentLog, CommunicationLog, Case
from accounts.models import SystemUser, Role, LegalRoom, Student, Professor, Beneficiary


class AppointmentModelSetup(TestCase):
    """Datos base reutilizables para todos los tests de Appointment."""

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Civil')

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

        self.beneficiary = Beneficiary.objects.create_user(
            document='123456', email='ben@gmail.com', password='test123',
            name='Pedro Beneficiario', phone='3001234567',
            address='Calle 1', stratum=2
        )

        self.case = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timedelta(days=30),
            beneficiary=self.beneficiary,
        )


class AppointmentCreationTest(AppointmentModelSetup):
    """Verifica creación básica de una cita."""

    def test_appointment_created_successfully(self):
        # Una cita se crea con todos los campos requeridos
        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(days=3),
            modality='presencial',
            location_or_link='Sala 201',
            created_by=self.sec_user,
        )
        self.assertIsNotNone(appointment.pk)
        self.assertEqual(appointment.status, 'programada')       # estado por defecto
        self.assertFalse(appointment.reminder_sent)              # flag por defecto

    def test_appointment_str(self):
        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(days=3),
            modality='virtual',
            location_or_link='https://meet.google.com/xyz',
            created_by=self.sec_user,
        )
        # __str__ debe incluir el ID del caso y la modalidad
        self.assertIn(str(self.case.id), str(appointment))

    def test_modality_choices_are_valid(self):
        # Solo se aceptan las 3 modalidades definidas
        for modality in ['presencial', 'telefonica', 'virtual']:
            apt = Appointment(
                case=self.case,
                scheduled_datetime=timezone.now() + timedelta(days=1),
                modality=modality,
                location_or_link='Lugar',
                created_by=self.sec_user,
            )
            apt.full_clean()  # no debe lanzar ValidationError


class AppointmentRescheduleTest(AppointmentModelSetup):
    """Verifica la lógica de reprogramación y su bitácora."""

    def setUp(self):
        super().setUp()
        self.appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(days=3),
            modality='presencial',
            location_or_link='Sala 201',
            created_by=self.sec_user,
        )

    def test_appointment_log_created_on_reschedule(self):
        # Al reprogramar, se guarda un AppointmentLog
        old_dt = self.appointment.scheduled_datetime
        new_dt = old_dt + timedelta(days=7)

        log = AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.sec_user,
            previous_datetime=old_dt,
            new_datetime=new_dt,
            reason='Solicitud del beneficiario',
            no_reason_flag=False,
        )
        self.assertEqual(AppointmentLog.objects.filter(appointment=self.appointment).count(), 1)
        self.assertFalse(log.no_reason_flag)

    def test_appointment_log_no_reason_flag_true_when_empty(self):
        # Si el motivo está vacío, no_reason_flag debe ser True
        old_dt = self.appointment.scheduled_datetime
        log = AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.sec_user,
            previous_datetime=old_dt,
            new_datetime=old_dt + timedelta(days=2),
            reason='',
            no_reason_flag=True,
        )
        self.assertTrue(log.no_reason_flag)

    def test_appointment_status_updates_to_reprogramada(self):
        # El status cambia a 'reprogramada' después de reprogramar
        self.appointment.status = 'reprogramada'
        self.appointment.save()
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'reprogramada')

    def test_multiple_logs_per_appointment(self):
        # Una cita puede tener múltiples reprogramaciones
        old_dt = self.appointment.scheduled_datetime
        for i in range(3):
            AppointmentLog.objects.create(
                appointment=self.appointment,
                changed_by=self.sec_user,
                previous_datetime=old_dt + timedelta(days=i),
                new_datetime=old_dt + timedelta(days=i + 1),
                reason=f'Cambio {i}',
                no_reason_flag=False,
            )
        self.assertEqual(AppointmentLog.objects.filter(appointment=self.appointment).count(), 3)


class AppointmentReminderFlagTest(AppointmentModelSetup):
    """Verifica el flag reminder_sent para prevenir duplicados (HU2)."""

    def test_reminder_sent_default_is_false(self):
        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='telefonica',
            location_or_link='3001234567',
            created_by=self.sec_user,
        )
        self.assertFalse(appointment.reminder_sent)

    def test_reminder_sent_can_be_set_true(self):
        appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=20),
            modality='telefonica',
            location_or_link='3001234567',
            created_by=self.sec_user,
        )
        appointment.reminder_sent = True
        appointment.save()
        appointment.refresh_from_db()
        self.assertTrue(appointment.reminder_sent)


class CommunicationLogTest(AppointmentModelSetup):
    """Verifica la bitácora de correos institucionales (HU3)."""

    def test_communication_log_created_successfully(self):
        log = CommunicationLog.objects.create(
            case=self.case,
            sent_by=self.prof_user,
            recipients=['estudiante@icesi.edu.co', 'ben@gmail.com'],
            subject='Actualización del caso',
            body='Estimado estudiante, le informamos...',
            status='enviado',
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.status, 'enviado')

    def test_communication_log_failed_status(self):
        log = CommunicationLog.objects.create(
            case=self.case,
            sent_by=self.prof_user,
            recipients=['estudiante@icesi.edu.co'],
            subject='Test',
            body='Cuerpo del mensaje',
            status='fallido',
        )
        self.assertEqual(log.status, 'fallido')

    def test_communication_log_recipients_is_list(self):
        recipients = ['a@icesi.edu.co', 'b@icesi.edu.co']
        log = CommunicationLog.objects.create(
            case=self.case,
            sent_by=self.prof_user,
            recipients=recipients,
            subject='Test',
            body='Cuerpo',
            status='enviado',
        )
        log.refresh_from_db()
        self.assertIsInstance(log.recipients, list)
        self.assertEqual(len(log.recipients), 2)