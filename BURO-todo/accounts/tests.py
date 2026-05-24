from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from .models import Beneficiary, SystemUser, Role, Student, Professor, LegalRoom
from cases.models import Case, GradeWeightConfig, AcademicAction, CaseLog
from cases.services import calculate_final_grade
from .utils import get_case_urgency, get_student_load_summary
from datetime import timedelta
from django.utils import timezone
from unittest.mock import patch
from accounts.utils import auto_assign_cases
from notifications.services import send_notification

#py manage.py test accounts

class RegistroEstudianteViewTest(TestCase):
    def setUp(self):
        self.staff = SystemUser.objects.create_user(
            email='staff-reg@icesi.edu.co',
            password='Staff123!',
            name='Staff Registro',
            is_staff=True,
        )

    def test_pagina_carga(self):
        """GET /accounts/register/student/ solo para staff."""
        self.assertEqual(self.client.get(reverse('accounts:register-student')).status_code, 403)
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        response = self.client.get(reverse('accounts:register-student'))
        self.assertEqual(response.status_code, 200)

    def test_registro_exitoso(self):
        """POST válido crea SystemUser + Student."""
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        response = self.client.post(reverse('accounts:register-student'), {
            'name': 'Ana López',
            'email': 'analopez@icesi.edu.co',
            'student_code': '2012345',
            'semester': 8,
            'password1': 'Segura123!',
            'password2': 'Segura123!',
        })
        self.assertEqual(response.status_code, 302)

    def test_correo_no_institucional_bloquea(self):
        """Correo sin @icesi.edu.co no permite registro."""
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        response = self.client.post(reverse('accounts:register-student'), {
            'name': 'Ana López',
            'email': 'analopez@gmail.com',
            'document': '1144567890',
            'student_code': '2012345',
            'semester': 8,
            'password1': 'Segura123!',
            'password2': 'Segura123!',
        })
        self.assertEqual(response.status_code, 200)

    def test_codigo_estudiantil_duplicado(self):
        """Código estudiantil ya registrado bloquea registro."""
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        user = SystemUser.objects.create_user(email='otro@icesi.edu.co', password='x', name='Otro')
        Student.objects.create(user=user, student_code='2012345', semester=5)

        response = self.client.post(reverse('accounts:register-student'), {
            'name': 'Ana López',
            'email': 'analopez@icesi.edu.co',
            'document': '1144567890',
            'student_code': '2012345',
            'semester': 8,
            'password1': 'Segura123!',
            'password2': 'Segura123!',
        })
        self.assertEqual(response.status_code, 200)

    def test_email_duplicado_bloquea(self):
        """Email ya registrado bloquea registro."""
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        SystemUser.objects.create_user(email='analopez@icesi.edu.co', password='x', name='Ana')

        response = self.client.post(reverse('accounts:register-student'), {
            'name': 'Otra Ana',
            'email': 'analopez@icesi.edu.co',
            'document': '1144567890',
            'student_code': '2012345',
            'semester': 8,
            'password1': 'Segura123!',
            'password2': 'Segura123!',
        })
        self.assertEqual(response.status_code, 200)

    def test_contrasenas_no_coinciden(self):
        """Contraseñas diferentes bloquea registro."""
        self.client.login(username='staff-reg@icesi.edu.co', password='Staff123!')
        response = self.client.post(reverse('accounts:register-student'), {
            'name': 'Ana López',
            'email': 'analopez@icesi.edu.co',
            'document': '1144567890',
            'student_code': '2012345',
            'semester': 8,
            'password1': 'Segura123!',
            'password2': 'OtraDistinta456!',
        })
        self.assertEqual(response.status_code, 200)
        

class RegistroBeneficiarioViewTest(TestCase):
       
    def setUp(self):
        """Create required test data: Professor, LegalRoom, and pending Cases."""
        # Create a professor (required by Case model)
        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='Prof123!',
            name='Profesor Test'
        )
        self.professor_role = Role.objects.create(name='Profesor')
        self.professor_user.role = self.professor_role
        self.professor_user.save()
        self.professor = Professor.objects.create(user=self.professor_user)
        
        # Create a legal room (required by Case model)
        self.legal_room = LegalRoom.objects.create(name='Sala Jurídica 1')
        
        # Create 2 pending cases with no assigned student
        from datetime import datetime, timedelta
        legal_deadline = datetime.now() + timedelta(days=30)
        
        Case.objects.create(
            number='CASO-001',
            description='Caso de prueba 1',
            professor=self.professor,
            room=self.legal_room,
            legal_deadline=legal_deadline,
            status='Pendiente',
            student=None
        )
        Case.objects.create(
            number='CASO-002',
            description='Caso de prueba 2',
            professor=self.professor,
            room=self.legal_room,
            legal_deadline=legal_deadline,
            status='Pendiente',
            student=None
        )

    def test_modal_exito_aparece_tras_registro_exitoso(self):
            """
            PTCJMGA-95 Criterio 1:
            Tras registro exitoso, el modal de éxito debe aparecer
            con el mensaje "Beneficiario registrado exitosamente".
            """
            response = self.client.post(reverse('accounts:register-beneficiary'), {
                'name': 'Laura Gómez',
                'document': '1088999777',
                'email': 'laura@email.com',
                'phone': '3101234567',
                'address': 'Carrera 10 #20-30',
                'date_of_birth': '1995-05-20',
                'stratum': 2,
                'password1': 'Segura123!',
                'password2': 'Segura123!',
                'data_authorization': True,
            }, follow=True)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'registrado exitosamente')
            self.assertContains(response, 'Iniciar Sesi')

    def test_modal_duplicado_aparece_con_documento_existente(self):
            """
            PTCJMGA-95 Criterio 2:
            Si el documento ya existe, el modal de advertencia debe aparecer
            con el mensaje "El usuario con ese documento ya se encuentra registrado".
            """
            Beneficiary.objects.create_user(
                document='1144567890',
                email='carlos@email.com',
                password='x',
                name='Carlos',
                phone='3001234567',
                address='Calle 5',
                stratum=2,
            )

            response = self.client.post(reverse('accounts:register-beneficiary'), {
                'name': 'Otro Nombre',
                'document': '1144567890',
                'email': 'otro@email.com',
                'phone': '3009999999',
                'address': 'Otra dirección',
                'date_of_birth': '2000-01-15',
                'stratum': 3,
                'password1': 'Segura123!',
                'password2': 'Segura123!',
                'data_authorization': True,
            })

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'El usuario con ese documento ya se encuentra registrado')

    def test_correo_duplicado_muestra_modal_warning(self):
            """
            PTCJMGA-95 Criterio 2 (variante correo):
            Si el correo ya existe, también aparece el modal de advertencia.
            """
            Beneficiary.objects.create_user(
                document='9999999999',
                email='repetido@email.com',
                password='x',
                name='Otro',
                phone='3000000000',
                address='Calle 1',
                stratum=1,
            )

            response = self.client.post(reverse('accounts:register-beneficiary'), {
                'name': 'Nuevo Beneficiario',
                'document': '1234567890',
                'email': 'repetido@email.com',
                'phone': '3001111111',
                'address': 'Calle 2',
                'date_of_birth': '1998-03-10',
                'stratum': 2,
                'password1': 'Segura123!',
                'password2': 'Segura123!',
                'data_authorization': True,
            })

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'ya se encuentra registrado')

    def test_errores_en_espanol_por_campo(self):
            """
            PTCJMGA-95 Criterio 3:
            Los mensajes de error de campos obligatorios deben estar en español.
            """
            response = self.client.post(reverse('accounts:register-beneficiary'), {
                'name': '',
                'document': '',
                'email': '',
                'phone': '',
                'address': '',
                'stratum': '',
                'password1': '',
                'password2': '',
                'data_authorization': False,
            })

            self.assertEqual(response.status_code, 200)
            form = response.context['form']
            self.assertIn('El nombre es obligatorio.', form.errors.get('name', []))
            self.assertIn('El documento es obligatorio.', form.errors.get('document', []))
            self.assertIn('El correo es obligatorio.', form.errors.get('email', []))
            self.assertIn('El teléfono es obligatorio.', form.errors.get('phone', []))
            
    def test_pagina_carga(self):
        """
        Prerrequisito: la página del formulario carga correctamente.
        GET /accounts/register/beneficiary/ → 200
        """
        response = self.client.get(reverse('accounts:register-beneficiary'))
        self.assertEqual(response.status_code, 200)

    def test_registro_exitoso_con_consentimiento(self):
        response = self.client.post(reverse('accounts:register-beneficiary'), {
            'name': 'Carlos Martínez',
            'document': '1144567890',
            'email': 'carlos@email.com',
            'phone': '3001234567',
            'address': 'Calle 5 #38-00, Cali',
            'date_of_birth': '2000-01-15',
            'stratum': 2,
            'password1': 'Segura123!',
            'password2': 'Segura123!',
            'data_authorization': True,
        })

        # DEBUG: ver qué errores tiene el form
        if response.status_code == 200:
            print("ERRORES:", response.context['form'].errors)

        # Verificar conteos
        pending_cases = Case.objects.filter(status='Pendiente', student__isnull=True).count()
        self.assertEqual(pending_cases, 2)


class CaseUrgencyAndLoadSummaryTest(TestCase):
    def setUp(self):
        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='Prof123!',
            name='Profesor Test'
        )
        self.professor_role = Role.objects.create(name='Profesor')
        self.professor_user.role = self.professor_role
        self.professor_user.save()
        self.professor = Professor.objects.create(user=self.professor_user)

        self.student_user = SystemUser.objects.create_user(
            email='estudiante@icesi.edu.co',
            password='Est123!',
            name='Estudiante Test'
        )
        self.student_role = Role.objects.create(name='Estudiante')
        self.student_user.role = self.student_role
        self.student_user.save()
        self.student = Student.objects.create(user=self.student_user, student_code='12345', semester=5)

        self.room = LegalRoom.objects.create(name='Sala Civil', description='Sala para casos civiles')

        today = timezone.localdate()
        self.case_overdue = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Asignado',
            legal_deadline=today - timedelta(days=1)
        )
        self.case_due_today = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Asignado',
            legal_deadline=today
        )
        self.case_two_days = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Asignado',
            legal_deadline=today + timedelta(days=2)
        )
        self.case_three_days = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Asignado',
            legal_deadline=today + timedelta(days=3)
        )
        self.case_four_days = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Asignado',
            legal_deadline=today + timedelta(days=4)
        )
        self.case_closed = Case.objects.create(
            professor=self.professor,
            room=self.room,
            student=self.student,
            status='Cerrado',
            legal_deadline=today + timedelta(days=1)
        )

    def test_get_case_urgency_levels(self):
        self.assertEqual(get_case_urgency(self.case_overdue), 'RED')
        self.assertEqual(get_case_urgency(self.case_due_today), 'RED')
        self.assertEqual(get_case_urgency(self.case_two_days), 'YELLOW')
        self.assertEqual(get_case_urgency(self.case_three_days), 'YELLOW')
        self.assertEqual(get_case_urgency(self.case_four_days), 'GREEN')

    def test_get_student_load_summary_counts_and_cases(self):
        summary = get_student_load_summary(self.student)

        self.assertEqual(summary['total_active_cases'], 5)
        self.assertEqual(summary['red_count'], 2)
        self.assertEqual(summary['yellow_count'], 2)
        self.assertEqual(summary['green_count'], 1)
        self.assertEqual(len(summary['cases']), 5)

        urgencies = {entry['case'].id: entry['urgency'] for entry in summary['cases']}
        self.assertEqual(urgencies[self.case_overdue.id], 'RED')
        self.assertEqual(urgencies[self.case_due_today.id], 'RED')
        self.assertEqual(urgencies[self.case_two_days.id], 'YELLOW')
        self.assertEqual(urgencies[self.case_three_days.id], 'YELLOW')
        self.assertEqual(urgencies[self.case_four_days.id], 'GREEN')

    def test_get_student_load_summary_excludes_closed_cases(self):
        summary = get_student_load_summary(self.student)
        self.assertNotIn(self.case_closed.id, [entry['case'].id for entry in summary['cases']])
        self.assertEqual(summary['total_active_cases'], 5)

class AutoAssignNotificationTest(TestCase):
    def setUp(self):
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

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

    @patch('notifications.services.send_notification')
    def test_notificacion_enviada_al_asignar_caso(self, mock_send):
        mock_send.return_value = True
        auto_assign_cases(self.professor_user)
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        self.assertEqual(kwargs['to'], self.student_user.email)

    @patch('notifications.services.send_notification')
    def test_asunto_correo_contiene_id_caso(self, mock_send):
        mock_send.return_value = True
        auto_assign_cases(self.professor_user)
        _, kwargs = mock_send.call_args
        self.assertIn('Nuevo caso asignado', kwargs['subject'])
        self.assertIn(str(self.case.id), kwargs['subject'])

    @patch('notifications.services.send_notification')
    def test_cuerpo_correo_contiene_datos_requeridos(self, mock_send):
        mock_send.return_value = True
        auto_assign_cases(self.professor_user)
        _, kwargs = mock_send.call_args
        self.assertIn(str(self.case.id), kwargs['body'])
        self.assertIn(self.beneficiary.name, kwargs['body'])
        self.assertIn(self.room.name, kwargs['body'])

    @patch('notifications.services.send_notification')
    def test_caselog_registrado_tras_asignacion(self, mock_send):
        mock_send.return_value = True

        auto_assign_cases(self.professor_user)

        log = CaseLog.objects.filter(case=self.case, event_type='asignacion').first()
        self.assertIsNotNone(log)

    @patch('notifications.services.send_notification')
    def test_fallo_notificacion_no_revierte_asignacion(self, mock_send):
        mock_send.side_effect = Exception('SMTP error')

        auto_assign_cases(self.professor_user)

        self.case.refresh_from_db()
        self.assertEqual(self.case.status, 'Asignado')
        self.assertIsNotNone(self.case.student)
        
# ============================================================
# PTCJMGA-55: Derecho al Olvido (Eliminación de Datos)
# Tests del modelo DataDeletionRequest
# ============================================================

from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import (
    Beneficiary,
    SystemUser,
    Role,
    DataDeletionRequest,
)


class DataDeletionRequestModelTest(TestCase):
    """
    Tests unitarios del modelo DataDeletionRequest (HU PTCJMGA-55).
    Validan:
    - Creación correcta con valores por defecto
    - Constantes de estado bien definidas
    - Relación con Beneficiary funciona
    - Auto-fechas y representación string
    """

    def setUp(self):
        """Crea un beneficiario base que se reutilizará en todos los tests."""
        self.beneficiary = Beneficiary.objects.create(
            name='Carlos Martínez',
            document='1144567890',
            email='carlos@email.com',
            phone='3001234567',
            address='Calle 5 #38-00, Cali',
            stratum=2,
            data_authorization=True,
        )

    # ---------- Creación y valores por defecto ----------

    def test_creacion_solicitud_con_estado_pendiente_por_defecto(self):
        """
        Al crear una solicitud sin especificar status, debe quedar en 'Pendiente'.
        Cubre: HU Escenario 1 — "registra la solicitud con fecha y estado Pendiente"
        """
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        self.assertEqual(request.status, 'Pendiente')
        self.assertEqual(request.status, DataDeletionRequest.STATUS_PENDIENTE)

    def test_creacion_solicitud_registra_fecha_automaticamente(self):
        """
        El campo requested_at debe asignarse automáticamente (auto_now_add).
        Cubre: HU Escenario 1 — "registra la solicitud con fecha"
        """
        antes  = timezone.now()
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)
        despues = timezone.now()

        self.assertIsNotNone(request.requested_at)
        self.assertGreaterEqual(request.requested_at, antes)
        self.assertLessEqual(request.requested_at, despues)

    def test_creacion_sin_motivo_es_valida(self):
        """El campo 'reason' es opcional (blank=True)."""
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        self.assertEqual(request.reason, '')

    def test_creacion_con_motivo_se_almacena(self):
        """Si el beneficiario da un motivo, debe guardarse."""
        motivo = 'Ya no quiero usar el servicio'
        request = DataDeletionRequest.objects.create(
            beneficiary=self.beneficiary,
            reason=motivo,
        )

        self.assertEqual(request.reason, motivo)

    # ---------- Estados (choices) ----------

    def test_constantes_de_estado_definidas(self):
        """Las constantes deben coincidir con las del modelo."""
        self.assertEqual(DataDeletionRequest.STATUS_PENDIENTE,  'Pendiente')
        self.assertEqual(DataDeletionRequest.STATUS_APROBADA,   'Aprobada')
        self.assertEqual(DataDeletionRequest.STATUS_RECHAZADA,  'Rechazada')
        self.assertEqual(DataDeletionRequest.STATUS_EJECUTADA,  'Ejecutada')

    def test_status_choices_contiene_los_cuatro_estados(self):
        """STATUS_CHOICES debe tener exactamente los 4 estados del flujo."""
        valores = [valor for valor, label in DataDeletionRequest.STATUS_CHOICES]

        self.assertIn('Pendiente',  valores)
        self.assertIn('Aprobada',   valores)
        self.assertIn('Rechazada',  valores)
        self.assertIn('Ejecutada',  valores)
        self.assertEqual(len(valores), 4)

    def test_cambio_de_estado_a_aprobada(self):
        """Una solicitud puede transicionar a 'Aprobada'."""
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)
        request.status = DataDeletionRequest.STATUS_APROBADA
        request.save()

        request.refresh_from_db()
        self.assertEqual(request.status, 'Aprobada')

    # ---------- Relación con Beneficiary ----------

    def test_relacion_con_beneficiary_via_related_name(self):
        """
        Debe poder consultarse las solicitudes desde el beneficiario
        usando el related_name='deletion_requests'.
        """
        DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        self.assertEqual(self.beneficiary.deletion_requests.count(), 1)

    def test_un_beneficiario_puede_tener_varias_solicitudes(self):
        """Si rechazaron una solicitud previa, se puede crear otra después."""
        DataDeletionRequest.objects.create(
            beneficiary=self.beneficiary,
            status=DataDeletionRequest.STATUS_RECHAZADA,
        )
        DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        self.assertEqual(self.beneficiary.deletion_requests.count(), 2)

    def test_eliminar_beneficiary_elimina_sus_solicitudes_cascade(self):
        """
        Si un beneficiario es eliminado físicamente, sus solicitudes también.
        on_delete=CASCADE configurado en el modelo.
        """
        DataDeletionRequest.objects.create(beneficiary=self.beneficiary)
        self.assertEqual(DataDeletionRequest.objects.count(), 1)

        self.beneficiary.delete()
        self.assertEqual(DataDeletionRequest.objects.count(), 0)

    # ---------- Campos de procesamiento ----------

    def test_processed_at_y_processed_by_son_nullables_inicialmente(self):
        """
        Al crear la solicitud (estado Pendiente), aún no ha sido procesada,
        por lo que processed_at y processed_by deben estar vacíos.
        """
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        self.assertIsNone(request.processed_at)
        self.assertIsNone(request.processed_by)

    def test_solicitud_aprobada_registra_procesador_y_fecha(self):
        """
        Cuando un admin aprueba, processed_by y processed_at deben actualizarse.
        Cubre: HU Escenario 2 — auditoría de quién procesó la solicitud
        """
        # Crear un admin que procesa
        admin = SystemUser.objects.create(
            name='Admin Test',
            email='admin@icesi.edu.co',
        )
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        # Simular aprobación
        request.status = DataDeletionRequest.STATUS_APROBADA
        request.processed_by = admin
        request.processed_at = timezone.now()
        request.save()

        request.refresh_from_db()
        self.assertEqual(request.processed_by, admin)
        self.assertIsNotNone(request.processed_at)

    def test_rechazo_registra_motivo(self):
        """
        Cuando se rechaza, debe guardarse el motivo del rechazo.
        Cubre: HU Escenario 3 — "No es posible eliminar sus datos mientras tenga casos activos"
        """
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        request.status = DataDeletionRequest.STATUS_RECHAZADA
        request.rejection_reason = 'No es posible eliminar sus datos mientras tenga casos activos'
        request.save()

        request.refresh_from_db()
        self.assertEqual(request.status, 'Rechazada')
        self.assertIn('casos activos', request.rejection_reason)

    # ---------- Representación y meta ----------

    def test_str_incluye_documento_estado_y_fecha(self):
        """El __str__ debe mostrar el documento del beneficiario, estado y fecha."""
        request = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        representacion = str(request)
        self.assertIn(self.beneficiary.document, representacion)
        self.assertIn('Pendiente', representacion)

    def test_ordering_por_fecha_descendente(self):
        """
        Las solicitudes más recientes deben aparecer primero
        (Meta.ordering = ['-requested_at']).
        """
        primera = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)
        segunda = DataDeletionRequest.objects.create(beneficiary=self.beneficiary)

        solicitudes = list(DataDeletionRequest.objects.all())
        self.assertEqual(solicitudes[0], segunda)
        self.assertEqual(solicitudes[1], primera)

    def test_db_table_es_solicitud_eliminacion(self):
        """La tabla en PostgreSQL debe llamarse 'solicitud_eliminacion'."""
        self.assertEqual(DataDeletionRequest._meta.db_table, 'solicitud_eliminacion')

# ============================================================
# PTCJMGA-50: Tests del servicio LegalReportGenerator
# ============================================================

from datetime import date, timedelta
from django.test import TestCase

from cases.models import Case
from accounts.models import LegalRoom, Professor, Student, Beneficiary, SystemUser, Role
from accounts.services.legal_report import LegalReportGenerator


class LegalReportGeneratorTest(TestCase):
    """
    Tests del servicio que genera reportes legales para entidades gubernamentales.
    Cubre los 2 escenarios Gherkin de la HU PTCJMGA-50.
    """

    def setUp(self):
        """Crea data minima para los tests: rol, sala, profesor, estudiante, beneficiario."""

        # Rol de profesor y estudiante (necesarios para SystemUser)
        self.role_professor = Role.objects.create(name='professor_test')
        self.role_student   = Role.objects.create(name='student_test')

        # Sala juridica
        self.sala_civil = LegalRoom.objects.create(name='Civil Test')

        # Profesor (necesita SystemUser primero)
        prof_user = SystemUser.objects.create(
            name='Profesor Test',
            email='prof.test@icesi.edu.co',
            role=self.role_professor,
        )
        self.profesor = Professor.objects.create(user=prof_user)

        # Estudiante
        stu_user = SystemUser.objects.create(
            name='Estudiante Test',
            email='estu.test@icesi.edu.co',
            role=self.role_student,
        )
        self.estudiante = Student.objects.create(
            user=stu_user,
            semester=8,
            student_code='ABC1234',
        )

        # Beneficiario
        self.beneficiario = Beneficiary.objects.create(
            name='Beneficiario Test',
            document='999999999',
            email='benef.test@email.com',
            phone='3001234567',
            address='Calle Test 123',
            stratum=2,
        )

    def _crear_caso(self, status='Cerrado', number='CASE-TEST-001', dias_atras=0):
        """Helper para crear casos rapidamente."""
        from django.utils import timezone
        caso = Case.objects.create(
            number=number,
            description='Caso de prueba',
            beneficiary=self.beneficiario,
            student=self.estudiante,
            professor=self.profesor,
            room=self.sala_civil,
            legal_deadline=date.today() + timedelta(days=30),
            status=status,
        )
        # Ajustar created_at si es necesario
        if dias_atras > 0:
            caso.created_at = timezone.now() - timedelta(days=dias_atras)
            caso.save()
        return caso

    # ---------- ESCENARIO 1: Reporte legal completo ----------

    def test_get_closed_cases_retorna_solo_cerrados(self):
        """
        Given existen casos cerrados en el sistema
        When el coordinador solicita el reporte legal
        Then el sistema retorna solo los casos en estado 'Cerrado'.
        """
        self._crear_caso(status='Cerrado',  number='CL-001')
        self._crear_caso(status='Pendiente', number='PE-001')
        self._crear_caso(status='Asignado',  number='AS-001')

        generator = LegalReportGenerator()
        resultados = generator.get_closed_cases()

        self.assertEqual(resultados.count(), 1)
        self.assertEqual(resultados.first().number, 'CL-001')

    def test_filtro_por_fecha_desde_excluye_anteriores(self):
        """Casos creados antes de date_from no aparecen."""
        self._crear_caso(status='Cerrado', number='OLD-001', dias_atras=30)
        self._crear_caso(status='Cerrado', number='NEW-001', dias_atras=5)

        date_from = date.today() - timedelta(days=10)
        generator = LegalReportGenerator(date_from=date_from)
        resultados = generator.get_closed_cases()

        numbers = list(resultados.values_list('number', flat=True))
        self.assertIn('NEW-001', numbers)
        self.assertNotIn('OLD-001', numbers)

    def test_sin_filtros_retorna_todos_los_cerrados(self):
        """Sin date_from ni date_to, retorna todos los casos cerrados."""
        self._crear_caso(status='Cerrado', number='C-001')
        self._crear_caso(status='Cerrado', number='C-002')
        self._crear_caso(status='Cerrado', number='C-003')

        generator = LegalReportGenerator()
        resultados = generator.get_closed_cases()

        self.assertEqual(resultados.count(), 3)

    # ---------- ESCENARIO 2: Validacion de datos ----------

    def test_caso_completo_no_aparece_en_incompletos(self):
        """Un caso con todos los campos obligatorios NO esta incompleto."""
        caso = self._crear_caso(status='Cerrado', number='COMPLETE-001')

        generator = LegalReportGenerator()
        incomplete = generator.detect_incomplete_cases([caso])

        self.assertEqual(len(incomplete), 0)

    def test_detecta_caso_sin_numero(self):
        """
        Given el reporte generado
        When se detectan datos incompletos (caso sin numero)
        Then el sistema lo marca como incompleto.
        """
        caso = self._crear_caso(status='Cerrado', number='WILL-CLEAR')
        caso.number = ''   # vaciar el numero
        caso.save()

        generator = LegalReportGenerator()
        incomplete = generator.detect_incomplete_cases([caso])

        self.assertEqual(len(incomplete), 1)
        self.assertIn('numero', incomplete[0]['missing_fields'])

    # ---------- Generacion del PDF ----------

    def test_pdf_se_genera_con_casos_existentes(self):
        """El PDF se construye sin errores cuando hay casos cerrados."""
        self._crear_caso(status='Cerrado', number='PDF-001')
        self._crear_caso(status='Cerrado', number='PDF-002')

        generator = LegalReportGenerator()
        cases = generator.get_closed_cases()
        buffer = generator.generate_pdf(cases, secretary_name='Test Secretary')

        # El buffer debe contener bytes (un PDF valido empieza con %PDF)
        content = buffer.getvalue()
        self.assertTrue(len(content) > 0)
        self.assertTrue(content.startswith(b'%PDF'))

    def test_pdf_se_genera_con_lista_vacia(self):
        """El PDF se genera correctamente incluso sin casos (muestra mensaje vacio)."""
        generator = LegalReportGenerator()
        cases = generator.get_closed_cases()  # vacio
        buffer = generator.generate_pdf(cases, secretary_name='Test Secretary')

        content = buffer.getvalue()
        self.assertTrue(content.startswith(b'%PDF'))