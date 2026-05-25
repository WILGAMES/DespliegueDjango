# cases/tests/test_hu3_institutional_email.py
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta

from cases.models import Case, CommunicationLog
from accounts.models import SystemUser, Role, LegalRoom, Student, Professor, Beneficiary


class HU3BaseSetup(TestCase):
    """Datos base para todos los tests de HU3."""

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Familia')

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
            user=self.stu_user, semester=5, student_code='A00456'
        )

        # Beneficiario
        self.beneficiary = Beneficiary.objects.create_user(
            document='555666', email='ben@gmail.com', password='test123',
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

        self.client = Client()


# ─── Tests de obtención de destinatarios ─────────────────────────────────────

class RecipientLoadingTest(HU3BaseSetup):
    """Verifica que los destinatarios del caso se cargan correctamente."""

    def test_recipients_endpoint_returns_student_and_beneficiary(self):
        """El endpoint retorna el estudiante y beneficiario del caso."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:email_recipients', args=[self.case.id])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        emails = [r['email'] for r in data['recipients']]
        self.assertIn('stu@icesi.edu.co', emails)
        self.assertIn('ben@gmail.com', emails)

    def test_recipients_endpoint_excludes_empty_emails(self):
        """Destinatarios sin correo no aparecen en la lista."""
        # Beneficiario sin correo
        self.beneficiary.email = ''
        self.beneficiary.save()

        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:email_recipients', args=[self.case.id])
        )
        data = response.json()
        emails = [r['email'] for r in data['recipients']]
        self.assertNotIn('', emails)

    def test_only_professor_can_access_recipients(self):
        """Solo el profesor puede ver los destinatarios."""
        self.client.login(email='sec@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:email_recipients', args=[self.case.id])
        )
        self.assertEqual(response.status_code, 403)


# ─── Tests de envío de correo ─────────────────────────────────────────────────

class SendEmailTest(HU3BaseSetup):
    """Verifica el envío de correos institucionales desde el caso."""

    @patch('cases.views.send_notification')
    def test_professor_can_send_email_successfully(self, mock_send):
        """El profesor puede enviar un correo a destinatarios válidos."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Actualización del caso',
                'body':       'Estimado estudiante, le informamos del avance.',
                'recipients': ['stu@icesi.edu.co', 'ben@gmail.com'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_send.call_count, 2)

    @patch('cases.views.send_notification')
    def test_communication_log_created_on_success(self, mock_send):
        """Se crea un CommunicationLog con status 'enviado' tras envío exitoso."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Recordatorio',
                'body':       'Por favor revise el documento adjunto.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        log = CommunicationLog.objects.filter(case=self.case).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'enviado')
        self.assertEqual(log.sent_by, self.prof_user)

    @patch('cases.views.send_notification', side_effect=Exception('SMTP error'))
    def test_communication_log_created_on_failure(self, mock_send):
        """Se crea un CommunicationLog con status 'fallido' si el envío falla."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Mensaje fallido',
                'body':       'Este correo no llegará.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        log = CommunicationLog.objects.filter(case=self.case).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'fallido')

    @patch('cases.views.send_notification', side_effect=Exception('SMTP error'))
    def test_failed_notification_created_on_send_error(self, mock_send):
        """Si el envío falla, se crea un FailedNotification."""
        from notifications.models import FailedNotification
        self.client.login(email='prof@icesi.edu.co', password='test123')
        self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Error test',
                'body':       'Cuerpo del mensaje.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        self.assertTrue(FailedNotification.objects.exists())

    def test_send_email_without_recipients_returns_400(self):
        """Enviar sin destinatarios retorna error 400."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Sin destinatarios',
                'body':       'Cuerpo del mensaje.',
                'recipients': [],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_send_email_without_subject_returns_400(self):
        """Enviar sin asunto retorna error 400."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    '',
                'body':       'Cuerpo del mensaje.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_secretaria_cannot_send_email(self):
        """La secretaria no puede enviar correos institucionales."""
        self.client.login(email='sec@icesi.edu.co', password='test123')
        response = self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Test',
                'body':       'Cuerpo.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cannot_send_email(self):
        """Usuario no autenticado es redirigido al login."""
        response = self.client.post(
            reverse('cases:send_case_email', args=[self.case.id]),
            {
                'subject':    'Test',
                'body':       'Cuerpo.',
                'recipients': ['stu@icesi.edu.co'],
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


# ─── Tests del historial de comunicaciones ───────────────────────────────────

class CommunicationHistoryViewTest(HU3BaseSetup):
    """Verifica la vista del historial de correos del caso."""

    def setUp(self):
        super().setUp()
        CommunicationLog.objects.create(
            case=self.case,
            sent_by=self.prof_user,
            recipients=['stu@icesi.edu.co'],
            subject='Primer correo',
            body='Contenido del primer correo.',
            status='enviado',
        )
        CommunicationLog.objects.create(
            case=self.case,
            sent_by=self.prof_user,
            recipients=['ben@gmail.com'],
            subject='Segundo correo',
            body='Contenido del segundo correo.',
            status='fallido',
        )

    def test_professor_can_view_communication_history(self):
        """El profesor puede ver el historial de correos del caso."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:communication_history', args=[self.case.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('logs', response.context)
        self.assertEqual(len(response.context['logs']), 2)

    def test_history_shows_failed_status(self):
        """El historial muestra el estado 'fallido' correctamente."""
        self.client.login(email='prof@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:communication_history', args=[self.case.id])
        )
        self.assertContains(response, 'fallido')

    def test_secretaria_cannot_view_history(self):
        """La secretaria no puede ver el historial de comunicaciones."""
        self.client.login(email='sec@icesi.edu.co', password='test123')
        response = self.client.get(
            reverse('cases:communication_history', args=[self.case.id])
        )
        self.assertEqual(response.status_code, 403)