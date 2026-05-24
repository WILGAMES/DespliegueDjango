from django.test import TestCase, Client
from unittest.mock import patch, MagicMock
from notifications.services import send_notification
from notifications.models import FailedNotification
from django.urls import reverse
from accounts.models import SystemUser, Role

class SendNotificationTest(TestCase):

    @patch('notifications.services.send_mail')
    def test_envio_exitoso_retorna_true(self, mock_send_mail):
        mock_send_mail.return_value = 1

        result = send_notification(
            to="estudiante@icesi.edu.co",
            subject="Test asunto",
            body="Test cuerpo"
        )

        self.assertTrue(result)

    @patch('notifications.services.send_mail')
    def test_send_mail_es_llamado_con_parametros_correctos(self, mock_send_mail):
        mock_send_mail.return_value = 1

        send_notification(
            to="estudiante@icesi.edu.co",
            subject="Test asunto",
            body="Test cuerpo"
        )

        mock_send_mail.assert_called_once_with(
            subject="Test asunto",
            message="Test cuerpo",
            from_email="buro.notifications@gmail.com",  # el valor real de tu .env
            recipient_list=["estudiante@icesi.edu.co"],
            fail_silently=False,
        )  

    @patch('notifications.services.send_mail')
    def test_fallo_en_envio_lanza_excepcion(self, mock_send_mail):
        mock_send_mail.side_effect = Exception("SMTP error")

        with self.assertRaises(Exception):
            send_notification(
                to="estudiante@icesi.edu.co",
                subject="Test asunto",
                body="Test cuerpo"
            )

class FailedNotificationModelTest(TestCase):

    def test_crear_failed_notification(self):
        notif = FailedNotification.objects.create(
            to='estudiante@icesi.edu.co',
            subject='Nuevo caso asignado — 1',
            body='Hola Ana, se te asignó el caso #1.',
            error_message='SMTP connection refused',
        )
        self.assertIsNotNone(notif.id)
        self.assertIsNotNone(notif.failed_at)
        self.assertFalse(notif.resolved)

    def test_estado_inicial_es_no_resuelto(self):
        notif = FailedNotification.objects.create(
            to='estudiante@icesi.edu.co',
            subject='Nuevo caso asignado — 1',
            body='Hola Ana, se te asignó el caso #1.',
            error_message='Timeout',
        )
        self.assertFalse(notif.resolved)
        self.assertIsNone(notif.resolved_at)

    def test_marcar_como_resuelto(self):
        notif = FailedNotification.objects.create(
            to='estudiante@icesi.edu.co',
            subject='Nuevo caso asignado — 1',
            body='Hola Ana, se te asignó el caso #1.',
            error_message='Timeout',
        )
        notif.resolved = True
        from django.utils import timezone
        notif.resolved_at = timezone.now()
        notif.save()

        notif.refresh_from_db()
        self.assertTrue(notif.resolved)
        self.assertIsNotNone(notif.resolved_at)

    def test_queryset_solo_pendientes(self):
        FailedNotification.objects.create(
            to='a@icesi.edu.co',
            subject='Asunto 1',
            body='Cuerpo 1',
            error_message='Error 1',
        )
        FailedNotification.objects.create(
            to='b@icesi.edu.co',
            subject='Asunto 2',
            body='Cuerpo 2',
            error_message='Error 2',
            resolved=True,
        )
        pendientes = FailedNotification.objects.filter(resolved=False)
        self.assertEqual(pendientes.count(), 1)


class FailedNotificationOnSendTest(TestCase):

    @patch('notifications.services.send_mail')
    def test_fallo_crea_failed_notification(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('SMTP error')

        from notifications.services import send_notification
        with self.assertRaises(Exception):
            send_notification(
                to='estudiante@icesi.edu.co',
                subject='Test asunto',
                body='Test cuerpo',
            )

        self.assertEqual(FailedNotification.objects.filter(resolved=False).count(), 1)
        notif = FailedNotification.objects.first()
        self.assertEqual(notif.to, 'estudiante@icesi.edu.co')
        self.assertIn('SMTP error', notif.error_message)

class FailedNotificationListViewTest(TestCase):

    def setUp(self):
        self.role_secretary = Role.objects.create(name='secretaria')
        self.role_student = Role.objects.create(name='STUDENT')

        self.coordinator = SystemUser.objects.create_user(
            email='coordinador@icesi.edu.co',
            password='test1234',
            name='Coordinadora',
            role=self.role_secretary,
        )
        self.student_user = SystemUser.objects.create_user(
            email='estudiante@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
        )

        FailedNotification.objects.create(
            to='a@icesi.edu.co',
            subject='Caso asignado',
            body='Cuerpo',
            error_message='Timeout',
        )
        FailedNotification.objects.create(
            to='b@icesi.edu.co',
            subject='Caso asignado 2',
            body='Cuerpo 2',
            error_message='SMTP error',
            resolved=True,
        )

    def test_coordinador_puede_ver_panel(self):
        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('notifications:failed-list'))
        self.assertEqual(response.status_code, 200)

    def test_panel_solo_muestra_pendientes(self):
        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('notifications:failed-list'))
        data = response.json()
        self.assertEqual(len(data['failed_notifications']), 1)
        self.assertEqual(data['failed_notifications'][0]['to'], 'a@icesi.edu.co')

    def test_no_coordinador_recibe_403(self):
        self.client.login(username='estudiante@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('notifications:failed-list'))
        self.assertEqual(response.status_code, 403)

    def test_no_autenticado_recibe_401(self):
        response = self.client.get(reverse('notifications:failed-list'))
        self.assertEqual(response.status_code, 401)


class RetryNotificationViewTest(TestCase):

    def setUp(self):
        self.role_secretary = Role.objects.create(name='secretaria')
        self.coordinator = SystemUser.objects.create_user(
            email='coordinador@icesi.edu.co',
            password='test1234',
            name='Coordinadora',
            role=self.role_secretary,
        )
        self.notif = FailedNotification.objects.create(
            to='estudiante@icesi.edu.co',
            subject='Caso asignado — 1',
            body='Hola Ana.',
            error_message='Timeout',
        )

    @patch('notifications.services.send_mail')
    def test_reintento_exitoso_marca_como_resuelto(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.post(
            reverse('notifications:retry', args=[self.notif.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.resolved)
        self.assertIsNotNone(self.notif.resolved_at)

    @patch('notifications.services.send_mail')
    def test_reintento_fallido_actualiza_error(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('Nuevo error SMTP')
        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.post(
            reverse('notifications:retry', args=[self.notif.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.resolved)
        self.assertIn('Nuevo error SMTP', self.notif.error_message)

    def test_no_coordinador_recibe_403_en_retry(self):
        role_student = Role.objects.create(name='STUDENT')
        student_user = SystemUser.objects.create_user(
            email='estudiante2@icesi.edu.co',
            password='test1234',
            name='Ana',
            role=role_student,
        )
        self.client.login(username='estudiante2@icesi.edu.co', password='test1234')
        response = self.client.post(
            reverse('notifications:retry', args=[self.notif.pk])
        )
        self.assertEqual(response.status_code, 403)