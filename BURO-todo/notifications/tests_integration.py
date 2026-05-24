from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone

from accounts.models import SystemUser, Role, LegalRoom, Professor, Student, Beneficiary
from accounts.utils import auto_assign_cases
from cases.models import Case, CaseLog
from notifications.models import FailedNotification


class AutoAssignNotificationIntegrationTest(TestCase):
    """
    Pruebas de integración para el flujo completo de asignación automática
    y notificaciones — desde la asignación hasta el correo y la bitácora.
    """

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_professor = Role.objects.create(name='profesor')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_secretary = Role.objects.create(name='secretaria')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.student_user = SystemUser.objects.create_user(
            email='estudiante@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            student_code='A00001',
        )

        self.coordinator_user = SystemUser.objects.create_user(
            email='coordinador@icesi.edu.co',
            password='test1234',
            name='Coordinadora',
            role=self.role_secretary,
        )

        self.beneficiary = Beneficiary.objects.create(
            name='Juan Beneficiario',
            document='123456789',
            email='beneficiario@gmail.com',
            phone='3001234567',
            address='Calle 1 #2-3',
            stratum=2,
            data_authorization=True,
        )

        self.case = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline='2026-12-31',
            status='Pendiente',
            beneficiary=self.beneficiary,
        )

    @patch('notifications.services.send_mail')
    def test_flujo_completo_asignacion_exitosa(self, mock_send_mail):
        """
        Dado un caso pendiente y un estudiante disponible,
        cuando el profesor dispara la asignación automática,
        entonces el caso se asigna, el correo se envía y la bitácora se registra.
        """
        mock_send_mail.return_value = 1

        auto_assign_cases(self.professor_user)

        # El caso fue asignado
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, 'Asignado')
        self.assertEqual(self.case.student, self.student)

        # El correo fue enviado
        mock_send_mail.assert_called_once()

        # La bitácora registró la asignación
        log = CaseLog.objects.filter(case=self.case, event_type='asignacion').first()
        self.assertIsNotNone(log)
        self.assertIn(self.student_user.name, log.description)

        # No hay notificaciones fallidas
        self.assertEqual(FailedNotification.objects.count(), 0)

    @patch('notifications.services.send_mail')
    def test_flujo_completo_fallo_notificacion_y_reintento(self, mock_send_mail):
        """
        Dado un fallo en el envío del correo,
        cuando el coordinador reintenta desde el panel,
        entonces el correo sale y la notificación fallida se marca como resuelta.
        """
        # Primera llamada falla, segunda tiene éxito
        mock_send_mail.side_effect = [Exception('SMTP error'), 1]

        auto_assign_cases(self.professor_user)

        # La asignación no se revirtió
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, 'Asignado')

        # Se creó una notificación fallida
        self.assertEqual(FailedNotification.objects.filter(resolved=False).count(), 1)

        # El coordinador reintenta desde el panel
        notif = FailedNotification.objects.filter(resolved=False).first()
        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.post(
            reverse('notifications:retry', args=[notif.pk])
        )
        self.assertEqual(response.status_code, 200)

        # La notificación queda marcada como resuelta
        notif.refresh_from_db()
        self.assertTrue(notif.resolved)
        self.assertIsNotNone(notif.resolved_at)

        # No quedan notificaciones pendientes
        self.assertEqual(FailedNotification.objects.filter(resolved=False).count(), 0)

    @patch('notifications.services.send_mail')
    def test_bitacora_registra_error_cuando_falla_notificacion(self, mock_send_mail):
        """
        Dado un fallo en el envío del correo,
        entonces el error queda registrado en la bitácora del caso.
        """
        mock_send_mail.side_effect = Exception('SMTP error')

        auto_assign_cases(self.professor_user)

        log_error = CaseLog.objects.filter(
            case=self.case,
            event_type='error_notificacion'
        ).first()
        self.assertIsNotNone(log_error)
        self.assertIn('SMTP error', log_error.description)

    @patch('notifications.services.send_mail')
    def test_coordinador_ve_notificaciones_fallidas_en_panel(self, mock_send_mail):
        """
        Dado un fallo en el envío,
        cuando el coordinador consulta el panel,
        entonces ve la notificación fallida con los datos correctos.
        """
        mock_send_mail.side_effect = Exception('SMTP error')

        auto_assign_cases(self.professor_user)

        self.client.login(username='coordinador@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('notifications:failed-list'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['failed_notifications']), 1)
        self.assertEqual(
            data['failed_notifications'][0]['to'],
            self.student_user.email
        )