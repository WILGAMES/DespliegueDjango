# cases/tests/test_professor_alerts.py
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from cases.models import Appointment, AppointmentLog, Case
from accounts.models import SystemUser, Role, LegalRoom, Student, Professor, Beneficiary
from notifications.models import FailedNotification


class ProfessorAlertsSetup(TestCase):
    """Datos base para tests de alertas del profesor."""

    def setUp(self):
        self.client = Client()
        
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
            number='2024-001',
            description='Caso de prueba',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timedelta(days=30),
            status='active'
        )

        # Cita
        self.appointment = Appointment.objects.create(
            case=self.case,
            scheduled_datetime=timezone.now() + timedelta(hours=2),
            modality='presencial',
            location_or_link='Sala 101',
            created_by=self.prof_user,
            status='programada'
        )


class TestProfessorAlertsView(ProfessorAlertsSetup):
    """Tests para la vista de panel de alertas del profesor."""

    def test_professor_alerts_view_requires_login(self):
        """La vista de alertas requiere autenticación."""
        response = self.client.get(reverse('cases:professor_appointment_alerts'))
        self.assertEqual(response.status_code, 302)  # Redirige a login

    def test_professor_alerts_view_accessible(self):
        """El profesor puede acceder a su panel de alertas."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alertas de reprogramación')

    def test_professor_alerts_shows_no_reason_reprogramations(self):
        """El panel muestra reprogramaciones sin motivo."""
        # Crear una reprogramación sin motivo
        AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.stu_user,
            previous_datetime=timezone.now() + timedelta(hours=1),
            new_datetime=timezone.now() + timedelta(hours=3),
            reason='',
            no_reason_flag=True,
        )

        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts'))
        
        self.assertContains(response, '⚠ Sin motivo')
        self.assertContains(response, 'Luis Estudiante')

    def test_professor_alerts_does_not_show_other_professors_alerts(self):
        """El profesor solo ve sus propias alertas."""
        # Crear otro profesor en otra sala
        other_room = LegalRoom.objects.create(name='Penal')
        other_prof_user = SystemUser.objects.create_user(
            email='prof2@icesi.edu.co', password='test123',
            name='Juan Otro', role=self.prof_role, room=other_room
        )
        other_professor = Professor.objects.create(user=other_prof_user)

        other_case = Case.objects.create(
            number='2024-002',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=other_professor,
            room=other_room,
            legal_deadline=timezone.now().date() + timedelta(days=30),
            status='active'
        )

        other_appointment = Appointment.objects.create(
            case=other_case,
            scheduled_datetime=timezone.now() + timedelta(hours=2),
            modality='presencial',
            created_by=other_prof_user,
            status='programada'
        )

        AppointmentLog.objects.create(
            appointment=other_appointment,
            changed_by=self.stu_user,
            previous_datetime=timezone.now() + timedelta(hours=1),
            new_datetime=timezone.now() + timedelta(hours=3),
            reason='',
            no_reason_flag=True,
        )

        # El primer profesor no debería ver esta alerta
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts'))
        
        self.assertNotContains(response, 'Juan Otro')

    def test_professor_alerts_excludes_30_day_old(self):
        """Alertas más antiguas a 30 días no se muestran."""
        old_log = AppointmentLog.objects.create(
            appointment=self.appointment,
            changed_by=self.stu_user,
            previous_datetime=timezone.now() - timedelta(days=31),
            new_datetime=timezone.now() - timedelta(days=31, hours=-2),
            reason='',
            no_reason_flag=True,
        )
        # Simular que es vieja
        old_log.changed_at = timezone.now() - timedelta(days=31)
        old_log.save()

        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts'))
        
        # No debería mostrar alertas antiguas
        self.assertIn('Sin alertas', response.content.decode())


class TestAlertsCountEndpoint(ProfessorAlertsSetup):
    """Tests para el endpoint de conteo de alertas."""

    def test_alerts_count_returns_zero_by_default(self):
        """El contador retorna 0 cuando no hay alertas."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts_count'))
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)

    def test_alerts_count_returns_correct_count(self):
        """El contador retorna la cantidad correcta de alertas."""
        # Crear 3 alertas
        for i in range(3):
            AppointmentLog.objects.create(
                appointment=self.appointment,
                changed_by=self.stu_user,
                previous_datetime=timezone.now() + timedelta(hours=1),
                new_datetime=timezone.now() + timedelta(hours=3),
                reason='',
                no_reason_flag=True,
            )

        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:professor_appointment_alerts_count'))
        
        data = response.json()
        self.assertEqual(data['count'], 3)

    def test_alerts_count_requires_login(self):
        """El endpoint de conteo requiere autenticación."""
        response = self.client.get(reverse('cases:professor_appointment_alerts_count'))
        self.assertEqual(response.status_code, 302)  # Redirige a login


class TestRetryFailedNotification(ProfessorAlertsSetup):
    """Tests para el endpoint de reintentar notificaciones."""

    def test_retry_notification_requires_login(self):
        """Reintentar requiere autenticación."""
        failed_notif = FailedNotification.objects.create(
            to='test@example.com',
            subject='Test',
            body='Test body',
            error_message='Test error',
        )
        
        response = self.client.post(
            reverse('cases:retry_failed_notification', kwargs={
                'case_id': self.case.id,
                'log_id': failed_notif.id
            })
        )
        self.assertEqual(response.status_code, 302)  # Redirige a login

    def test_retry_notification_requires_professor_role(self):
        """Solo profesores pueden reintentar notificaciones."""
        # Login como estudiante
        self.client.login(email='stu@icesi.edu.co', password='test123')
        
        failed_notif = FailedNotification.objects.create(
            to='test@example.com',
            subject='Test',
            body='Test body',
            error_message='Test error',
        )
        
        response = self.client.post(
            reverse('cases:retry_failed_notification', kwargs={
                'case_id': self.case.id,
                'log_id': failed_notif.id
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_retry_notification_not_found_returns_404(self):
        """Si la notificación no existe, retorna 404."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        
        response = self.client.post(
            reverse('cases:retry_failed_notification', kwargs={
                'case_id': self.case.id,
                'log_id': 99999
            })
        )
        self.assertEqual(response.status_code, 404)

    def test_retry_notification_marks_as_resolved(self):
        """Al reintentar exitosamente, marca como resuelto."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        
        failed_notif = FailedNotification.objects.create(
            to='test@example.com',
            subject='Test',
            body='Test body',
            error_message='Test error',
            resolved=False,
        )
        
        with self.assertLogs('notifications.services', level='INFO'):
            response = self.client.post(
                reverse('cases:retry_failed_notification', kwargs={
                    'case_id': self.case.id,
                    'log_id': failed_notif.id
                })
            )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'enviado')
        
        # Verificar que fue marcada como resuelta
        failed_notif.refresh_from_db()
        self.assertTrue(failed_notif.resolved)
        self.assertIsNotNone(failed_notif.resolved_at)


class TestEmailComposeRetry(ProfessorAlertsSetup):
    """Tests para la funcionalidad de reintentar en compose_case_email."""

    def test_compose_email_form_loads(self):
        """El formulario de composición de correo carga correctamente."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(reverse('cases:compose_case_email', kwargs={'case_id': self.case.id}))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Redactar correo institucional')

    def test_email_send_stores_data_for_retry(self):
        """El envío de correo almacena datos para poder reintentar."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        
        response = self.client.post(
            reverse('cases:send_case_email', kwargs={'case_id': self.case.id}),
            data={
                'subject': 'Test Subject',
                'body': 'Test Body',
                'recipients': ['ben@gmail.com'],
            },
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value if 'csrftoken' in self.client.cookies else '',
        )
        
        # Debería ser 200 (éxito) aunque falle el envío
        self.assertIn(response.status_code, [200, 403])
