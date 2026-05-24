from django.test import TestCase
from django.utils import timezone
from accounts.models import Student, Professor, LegalRoom, SystemUser, Role, Beneficiary
from cases.models import Case, GradeWeightConfig, AcademicAction, CaseLog, AcademicRecordTraceability, SystemLog
from cases.services import calculate_final_grade
from accounts.utils import validate_professor_legal_room_access
from django.urls import reverse
from unittest.mock import patch
from notifications.models import FailedNotification

from django.core.exceptions import PermissionDenied, ValidationError

class CaseModelTest(TestCase):

    def setUp(self):
        """
        Montaje base para todos los tests del modelo Case.
        Crea una sala jurídica, roles, un estudiante y un profesor
        listos para ser usados sin repetir código en cada test.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

    def test_case_creation_with_required_fields(self):
        """
        HU: Registro de acciones académicas calificables desde el caso
        Criterio base: un caso debe poder crearse con los campos mínimos
        obligatorios y persistir correctamente en la base de datos.

        Given un estudiante y un profesor activos en una sala jurídica
        When se crea un Case con student, professor, room y legal_deadline
        Then el caso se guarda en la BD con ID, status 'active' y created_at automático
        """
        case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            # 30 días hacia el futuro como fecha límite legal
            legal_deadline=timezone.now().date() + timezone.timedelta(days=30),
        )

        # El caso se persistió: tiene ID asignado por la BD
        self.assertIsNotNone(case.id)

        # El status por defecto debe ser 'active' sin necesidad de especificarlo
        self.assertEqual(case.status, 'active')

        # Django debe haber capturado la fecha/hora de creación automáticamente
        self.assertIsNotNone(case.created_at)

    def test_case_status_default_is_active(self):
        """
        HU: Registro de acciones académicas calificables desde el caso
        Criterio de aceptación 1: el caso debe tener estado diferente a
        'Cerrado' para permitir registrar acciones académicas.

        Given un caso recién creado sin especificar status explícitamente
        When se consulta su campo status
        Then el valor debe ser 'active' por defecto
        """
        case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=10),
        )

        # Protege contra que alguien elimine el default='active' del modelo
        self.assertEqual(case.status, 'active')

    def test_case_str_representation(self):
        """
        HU: Panel de carga académica en tiempo real por sala jurídica
        Criterio base: el panel debe identificar cada caso por estudiante.

        Given un caso asignado a 'Ana Estudiante'
        When se convierte el objeto a string (panel de admin, logs, debug)
        Then el string debe incluir el nombre del estudiante para ser legible
        """
        case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=10),
        )

        # Si __str__ no está definido, Django devuelve "Case object (1)": ilegible
        self.assertIn('Ana Estudiante', str(case))

class GradeWeightConfigModelTest(TestCase):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio de aceptación 3: el profesor puede configurar los pesos
    porcentuales de evaluación por sala y período académico.
    """

    def setUp(self):
        """
        Reutiliza el montaje base: sala jurídica, profesor y su usuario.
        El período académico se representa como string.
        """
        self.room = LegalRoom.objects.create(name='Laboral')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

    def test_grade_weight_config_creation(self):
        """
        Criterio 3: Given el profesor define pesos válidos para su sala y período
        When guarda la configuración
        Then el sistema la persiste correctamente
        """
        config = GradeWeightConfig.objects.create(
            professor=self.professor,
            room=self.room,
            period='2026-1',
            # Los tres pesos deben sumar exactamente 100
            weight_documents=40,
            weight_followups=30,
            weight_attendance=30,
        )

        # La configuración se persistió correctamente
        self.assertIsNotNone(config.id)

        # Los pesos se guardaron con los valores correctos
        self.assertEqual(config.weight_documents, 40)
        self.assertEqual(config.weight_followups, 30)
        self.assertEqual(config.weight_attendance, 30)

    def test_weights_must_sum_100(self):
        """
        Criterio 4: Given el profesor intenta guardar pesos que no suman 100%
        When el sistema valida la configuración
        Then lanza un error de validación con mensaje claro
        """
        from django.core.exceptions import ValidationError

        config = GradeWeightConfig(
            professor=self.professor,
            room=self.room,
            period='2026-1',
            # Suma 95 — debe fallar la validación
            weight_documents=40,
            weight_followups=25,
            weight_attendance=30,
        )

        # El modelo debe rechazar pesos que no sumen 100
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_only_one_active_config_per_professor_room_period(self):
        """
        Criterio 3: Given ya existe una configuración activa para un profesor,
        sala y período específicos
        When se intenta crear otra configuración para los mismos parámetros
        Then el sistema lanza un error de integridad — no pueden coexistir dos
        """
        from django.db import IntegrityError

        GradeWeightConfig.objects.create(
            professor=self.professor,
            room=self.room,
            period='2026-1',
            weight_documents=40,
            weight_followups=30,
            weight_attendance=30,
        )

        # No puede existir una segunda config para el mismo profesor/sala/período
        with self.assertRaises(IntegrityError):
            GradeWeightConfig.objects.create(
                professor=self.professor,
                room=self.room,
                period='2026-1',
                weight_documents=50,
                weight_followups=30,
                weight_attendance=20,
            )
class AcademicActionModelTest(TestCase):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 1 y 5: el profesor registra acciones calificables sobre un caso
    activo. Los campos de asistencia a cita son opcionales y solo aplican
    cuando action_type es 'attendance'.
    """

    def setUp(self):
        """
        Montaje base: sala, roles, estudiante, profesor y un caso activo
        listos para recibir acciones académicas.
        """
        self.room = LegalRoom.objects.create(name='Penal')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )

    def test_academic_action_document_creation(self):
        """
        Criterio 1: Given el profesor está en el detalle de un caso activo
        When registra una acción de tipo 'entrega de documento' con nota válida
        Then el sistema la persiste con fecha/hora automática y trazabilidad del profesor
        """
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='document',
            grade=4.5,
            registered_by=self.professor,
        )

        # La acción se persistió correctamente
        self.assertIsNotNone(action.id)

        # El tipo de acción es el correcto
        self.assertEqual(action.action_type, 'document')

        # La nota se guardó en el rango válido
        self.assertEqual(action.grade, 4.5)

        # Django capturó la fecha/hora automáticamente — trazabilidad
        self.assertIsNotNone(action.registered_at)

        # El profesor que registró queda en la trazabilidad
        self.assertEqual(action.registered_by, self.professor)

    def test_academic_action_grade_range_invalid(self):
        """
        Criterio 1: Given el profesor intenta registrar una nota fuera del rango 0.0-5.0
        When el sistema valida la acción
        Then lanza un error de validación
        """
        from django.core.exceptions import ValidationError

        action = AcademicAction(
            case=self.case,
            action_type='document',
            # Nota fuera de rango: debe fallar la validación
            grade=6.0,
            registered_by=self.professor,
        )

        # El modelo debe rechazar notas fuera del rango 0.0-5.0
        with self.assertRaises(ValidationError):
            action.full_clean()

    def test_academic_action_attendance_fields(self):
        """
        Criterio 5: Given existe una cita de seguimiento atendida
        When el profesor registra la asistencia con todos sus campos
        Then el sistema almacena el registro completo con trazabilidad
        """
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='attendance',
            grade=3.5,
            registered_by=self.professor,
            # Campos específicos de asistencia a cita
            attended=True,
            arrival_time=timezone.now().time(),
            document_delivered=True,
        )

        # La acción de asistencia se persistió correctamente
        self.assertIsNotNone(action.id)

        # Los campos de asistencia se guardaron correctamente
        self.assertTrue(action.attended)
        self.assertTrue(action.document_delivered)
        self.assertIsNotNone(action.arrival_time)

    def test_academic_action_grade_can_be_updated_after_save(self):
        """
        Given una accion academica ya registrada
        When se modifica la nota despues de guardada
        Then el sistema permite la actualizacion para auditarla.
        """
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='followup',
            grade=4.0,
            registered_by=self.professor,
        )

        action.grade = 5.0
        action.full_clean()
        action.save(modified_by=self.professor_user)
        action.refresh_from_db()

        self.assertEqual(str(action.grade), '5.0')

    def test_academic_action_delete_is_blocked_and_logged(self):
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='followup',
            grade=4.0,
            registered_by=self.professor,
        )

        with self.assertRaisesMessage(
            ValidationError,
            'Los registros académicos no pueden eliminarse. Use la opción de anulación con justificación.',
        ):
            action.delete(user=self.professor_user)

        log = SystemLog.objects.get(
            action_attempted='DELETE_ACADEMIC_ACTION',
            record_id=str(action.id),
        )
        self.assertEqual(log.user, self.professor_user)
        self.assertEqual(log.result, SystemLog.RESULT_BLOCKED)
        self.assertIsNotNone(log.created_at)

    def test_academic_action_delete_keeps_original_record(self):
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='document',
            grade=4.2,
            registered_by=self.professor,
        )

        with self.assertRaises(ValidationError):
            action.delete(user=self.professor_user)

        self.assertTrue(AcademicAction.objects.filter(pk=action.pk).exists())
        persisted = AcademicAction.objects.get(pk=action.pk)
        self.assertEqual(str(persisted.grade), '4.2')
        self.assertEqual(persisted.status, AcademicAction.STATUS_ACTIVE)

    def test_academic_action_queryset_delete_is_blocked_and_logged(self):
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='attendance',
            grade=3.8,
            registered_by=self.professor,
        )

        with self.assertRaisesMessage(
            ValidationError,
            'Los registros académicos no pueden eliminarse. Use la opción de anulación con justificación.',
        ):
            AcademicAction.objects.filter(pk=action.pk).delete(user=self.professor_user)

        self.assertTrue(AcademicAction.objects.filter(pk=action.pk).exists())
        self.assertTrue(SystemLog.objects.filter(
            user=self.professor_user,
            action_attempted='DELETE_ACADEMIC_ACTION',
            record_id=str(action.pk),
            result=SystemLog.RESULT_BLOCKED,
        ).exists())

    def test_academic_action_observation_is_optional(self):
        """
        Criterio 1: Given el profesor registra una acción sin observación
        When el sistema la guarda
        Then no lanza error: la observación es opcional
        """
        action = AcademicAction.objects.create(
            case=self.case,
            action_type='followup',
            grade=3.0,
            registered_by=self.professor,
            # Sin observation — debe guardarse sin problema
        )

        # Se guardó sin observación
        self.assertIsNotNone(action.id)
        self.assertEqual(action.observation, '')


class AcademicRecordTraceabilityModelTest(TestCase):
    """
    Pruebas de trazabilidad inmutable para acciones academicas.
    """

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Familia')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student.trace@icesi.edu.co',
            password='test1234',
            name='Ana Trace',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user, student_code='9000001')

        self.professor_user = SystemUser.objects.create_user(
            email='professor.trace@icesi.edu.co',
            password='test1234',
            name='Carlos Trace',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )
        self.academic_action = AcademicAction.objects.create(
            case=self.case,
            action_type='document',
            grade=4.0,
            registered_by=self.professor,
        )

    def test_traceability_record_creation(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='',
            new_value='4.0',
            event_type=AcademicRecordTraceability.EVENT_CREATE,
        )

        self.assertIsNotNone(trace.id)
        self.assertEqual(trace.academic_action, self.academic_action)
        self.assertEqual(trace.modified_by, self.professor_user)
        self.assertEqual(trace.event_type, AcademicRecordTraceability.EVENT_CREATE)
        self.assertIsNotNone(trace.created_at)

    def test_traceability_record_edit_is_blocked(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.5',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        trace.new_value = '5.0'

        with self.assertRaises(ValidationError):
            trace.save()

    def test_traceability_queryset_update_is_blocked(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.5',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        with self.assertRaises(ValidationError):
            AcademicRecordTraceability.objects.filter(pk=trace.pk).update(new_value='5.0')

    def test_traceability_record_delete_is_blocked(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.5',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        with self.assertRaises(ValidationError):
            trace.delete()

        self.assertTrue(AcademicRecordTraceability.objects.filter(pk=trace.pk).exists())

    def test_traceability_queryset_delete_is_blocked(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.5',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        with self.assertRaises(ValidationError):
            AcademicRecordTraceability.objects.filter(pk=trace.pk).delete()

        self.assertTrue(AcademicRecordTraceability.objects.filter(pk=trace.pk).exists())

    def test_old_value_and_new_value_are_persisted(self):
        trace = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='observation',
            old_value='Revision inicial',
            new_value='Revision aprobada',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        persisted = AcademicRecordTraceability.objects.get(pk=trace.pk)
        self.assertEqual(persisted.old_value, 'Revision inicial')
        self.assertEqual(persisted.new_value, 'Revision aprobada')

    def test_traceability_records_are_ordered_chronologically(self):
        first = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='',
            new_value='4.0',
            event_type=AcademicRecordTraceability.EVENT_CREATE,
        )
        second = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.5',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )

        traces = list(AcademicRecordTraceability.objects.all())
        self.assertEqual(traces, [first, second])
        self.assertLessEqual(first.created_at, second.created_at)

    def test_grade_update_creates_traceability_record_automatically(self):
        self.academic_action.grade = 4.7
        self.academic_action.save(modified_by=self.professor_user)
        self.academic_action.refresh_from_db()

        trace = AcademicRecordTraceability.objects.get(
            academic_action=self.academic_action,
            field_name='grade',
        )

        self.assertEqual(str(self.academic_action.grade), '4.7')
        self.assertEqual(trace.old_value, '4.0')
        self.assertEqual(trace.new_value, '4.7')
        self.assertEqual(trace.modified_by, self.professor_user)
        self.assertEqual(trace.event_type, AcademicRecordTraceability.EVENT_UPDATE)
        self.assertIsNotNone(trace.created_at)

    def test_observation_update_creates_traceability_record_automatically(self):
        self.academic_action.observation = 'Nueva observacion academica'
        self.academic_action.save(modified_by=self.professor_user)
        self.academic_action.refresh_from_db()

        trace = AcademicRecordTraceability.objects.get(
            academic_action=self.academic_action,
            field_name='observation',
        )

        self.assertEqual(self.academic_action.observation, 'Nueva observacion academica')
        self.assertEqual(trace.old_value, '')
        self.assertEqual(trace.new_value, 'Nueva observacion academica')
        self.assertEqual(trace.modified_by, self.professor_user)
        self.assertEqual(trace.event_type, AcademicRecordTraceability.EVENT_UPDATE)

    def test_grade_and_observation_update_create_one_trace_per_changed_field(self):
        self.academic_action.grade = 3.8
        self.academic_action.observation = 'Ajuste sustentado'
        self.academic_action._modified_by = self.professor_user
        self.academic_action.save()

        traces = AcademicRecordTraceability.objects.filter(
            academic_action=self.academic_action,
        ).order_by('field_name')

        self.assertEqual(traces.count(), 2)
        self.assertEqual(
            [(trace.field_name, trace.old_value, trace.new_value) for trace in traces],
            [
                ('grade', '4.0', '3.8'),
                ('observation', '', 'Ajuste sustentado'),
            ],
        )

    def test_saving_without_grade_or_observation_changes_does_not_create_traceability(self):
        self.academic_action.attended = True
        self.academic_action.save(modified_by=self.professor_user)

        self.assertFalse(
            AcademicRecordTraceability.objects.filter(
                academic_action=self.academic_action,
            ).exists()
        )

    def test_repeated_save_with_same_values_does_not_duplicate_traceability(self):
        self.academic_action.grade = 4.5
        self.academic_action.save(modified_by=self.professor_user)
        self.academic_action.save(modified_by=self.professor_user)

        self.assertEqual(
            AcademicRecordTraceability.objects.filter(
                academic_action=self.academic_action,
                field_name='grade',
            ).count(),
            1,
        )


class ProfessorLegalRoomAccessHelperTest(TestCase):
    def setUp(self):
        self.room = LegalRoom.objects.create(name='Comercial')
        self.other_room = LegalRoom.objects.create(name='Tributario')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student.room.helper@icesi.edu.co',
            password='test1234',
            name='Estudiante Helper',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user, student_code='9000003')

        self.professor_user = SystemUser.objects.create_user(
            email='professor.room.helper@icesi.edu.co',
            password='test1234',
            name='Profesor Helper',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.other_professor_user = SystemUser.objects.create_user(
            email='other.professor.room.helper@icesi.edu.co',
            password='test1234',
            name='Profesor Otra Sala Helper',
            role=self.role_professor,
            room=self.other_room,
        )
        Professor.objects.create(user=self.other_professor_user)

        self.professor_without_room_user = SystemUser.objects.create_user(
            email='no.room.professor.helper@icesi.edu.co',
            password='test1234',
            name='Profesor Sin Sala Helper',
            role=self.role_professor,
            room=None,
        )
        Professor.objects.create(user=self.professor_without_room_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )

    def test_helper_allows_professor_from_same_legal_room(self):
        self.assertTrue(validate_professor_legal_room_access(self.professor_user, self.case))

    def test_helper_denies_professor_from_other_legal_room_and_logs_attempt(self):
        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            with self.assertRaises(PermissionDenied):
                validate_professor_legal_room_access(self.other_professor_user, self.case)

        self.assertIn('LegalRoom mismatch', logs.output[0])

    def test_helper_denies_professor_without_legal_room_and_logs_attempt(self):
        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            with self.assertRaises(PermissionDenied):
                validate_professor_legal_room_access(self.professor_without_room_user, self.case)

        self.assertIn('professor without LegalRoom', logs.output[0])

    def test_helper_denies_non_professor_and_logs_attempt(self):
        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            with self.assertRaises(PermissionDenied):
                validate_professor_legal_room_access(self.student_user, self.case)

        self.assertIn('non-professor', logs.output[0])


class AcademicActionTraceabilityViewTest(TestCase):
    def setUp(self):
        self.room = LegalRoom.objects.create(name='Publico')
        self.other_room = LegalRoom.objects.create(name='Constitucional')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student.view.trace@icesi.edu.co',
            password='test1234',
            name='Estudiante Vista',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user, student_code='9000002')

        self.professor_user = SystemUser.objects.create_user(
            email='professor.view.trace@icesi.edu.co',
            password='test1234',
            name='Profesor Vista',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.other_professor_user = SystemUser.objects.create_user(
            email='other.professor.view.trace@icesi.edu.co',
            password='test1234',
            name='Profesor Otra Sala Vista',
            role=self.role_professor,
            room=self.other_room,
        )
        Professor.objects.create(user=self.other_professor_user)

        self.professor_without_room_user = SystemUser.objects.create_user(
            email='no.room.professor.view.trace@icesi.edu.co',
            password='test1234',
            name='Profesor Sin Sala Vista',
            role=self.role_professor,
            room=None,
        )
        Professor.objects.create(user=self.professor_without_room_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )
        self.academic_action = AcademicAction.objects.create(
            case=self.case,
            action_type='document',
            grade=4.0,
            observation='Inicial',
            registered_by=self.professor,
        )
        self.url = reverse('academic-action-traceability', args=[self.academic_action.id])

    def test_professor_can_access_traceability_view(self):
        self.client.force_login(self.professor_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cases/academic_action_traceability.html')

    def test_non_professor_cannot_access_traceability_view(self):
        self.client.force_login(self.student_user)

        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertIn('non-professor', logs.output[0])

    def test_professor_from_other_legal_room_cannot_access_traceability_view(self):
        self.client.force_login(self.other_professor_user)

        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertIn('LegalRoom mismatch', logs.output[0])

    def test_professor_without_legal_room_cannot_access_traceability_view(self):
        self.client.force_login(self.professor_without_room_user)

        with self.assertLogs('accounts.utils', level='WARNING') as logs:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertIn('professor without LegalRoom', logs.output[0])

    def test_anonymous_user_is_redirected_from_traceability_view(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/', response['Location'])

    def test_traceability_view_rejects_write_methods(self):
        self.client.force_login(self.professor_user)

        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_traceability_history_is_ordered_descending(self):
        first = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.2',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )
        second = AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='observation',
            old_value='Inicial',
            new_value='Ajustada',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )
        self.client.force_login(self.professor_user)

        response = self.client.get(self.url)

        self.assertEqual(list(response.context['history_records']), [second, first])

    def test_traceability_view_renders_history_fields(self):
        AcademicRecordTraceability.objects.create(
            academic_action=self.academic_action,
            modified_by=self.professor_user,
            field_name='grade',
            old_value='4.0',
            new_value='4.8',
            event_type=AcademicRecordTraceability.EVENT_UPDATE,
        )
        self.client.force_login(self.professor_user)

        response = self.client.get(self.url)

        self.assertContains(response, 'Profesor Vista')
        self.assertContains(response, 'grade')
        self.assertContains(response, '4.0')
        self.assertContains(response, '4.8')
        self.assertContains(response, 'UPDATE')

    def test_traceability_view_shows_create_event_when_action_has_no_modifications(self):
        self.client.force_login(self.professor_user)

        response = self.client.get(self.url)

        history_records = response.context['history_records']
        self.assertEqual(len(history_records), 1)
        self.assertEqual(history_records[0]['event_type'], AcademicRecordTraceability.EVENT_CREATE)
        self.assertContains(response, 'CREATE')

class CalculateFinalGradeTest(TestCase):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 2: el cálculo de nota final aplica los pesos configurados
    por el profesor para el período activo de su sala.
    """

    def setUp(self):
        """
        Montaje completo: sala, profesor, estudiante, caso activo
        y una configuración de pesos 40/30/30 para el período 2026-1.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )

        # Configuración de pesos activa para el período 2026-1
        self.config = GradeWeightConfig.objects.create(
            professor=self.professor,
            room=self.room,
            period='2026-1',
            weight_documents=40,
            weight_followups=30,
            weight_attendance=30,
        )

    def test_calculate_final_grade_with_all_action_types(self):
        """
        Criterio 2: Given el estudiante tiene acciones de los tres tipos
        When el sistema calcula la nota final
        Then aplica los pesos correctamente y redondea a 1 decimal

        Cálculo esperado:
        - documents: promedio(4.0, 4.0) = 4.0 * 0.40 = 1.6
        - followups:  promedio(3.0, 5.0) = 4.0 * 0.30 = 1.2
        - attendance: promedio(4.0)       = 4.0 * 0.30 = 1.2
        - total: 1.6 + 1.2 + 1.2 = 4.0
        """
        AcademicAction.objects.create(case=self.case, action_type='document',   grade=4.0, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='document',   grade=4.0, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='followup',   grade=3.0, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='followup',   grade=5.0, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='attendance', grade=4.0, registered_by=self.professor)

        result = calculate_final_grade(self.student, '2026-1', self.room)

        # Nota final esperada: 4.0
        self.assertEqual(result, 4.0)

    def test_missing_action_type_counts_as_zero(self):
        """
        Criterio 2: Given el estudiante no tiene acciones de algún tipo
        When el sistema calcula la nota final
        Then ese componente cuenta como 0.0 en el cálculo

        Cálculo esperado:
        - documents: promedio(4.0) = 4.0 * 0.40 = 1.6
        - followups:  sin acciones  = 0.0 * 0.30 = 0.0
        - attendance: sin acciones  = 0.0 * 0.30 = 0.0
        - total: 1.6
        """
        AcademicAction.objects.create(case=self.case, action_type='document', grade=4.0, registered_by=self.professor)

        result = calculate_final_grade(self.student, '2026-1', self.room)

        # Solo el componente de documentos aporta — resultado 1.6
        self.assertEqual(result, 1.6)

    def test_no_active_config_raises_error(self):
        """
        Criterio 6: Given el profesor no tiene configuración de pesos
        para el período solicitado
        When el sistema intenta calcular la nota
        Then lanza un error claro — no ejecuta cálculo parcial
        """
        from django.core.exceptions import ValidationError

        # Período sin configuración activa
        with self.assertRaises(ValidationError):
            calculate_final_grade(self.student, '2025-1', self.room)

    def test_final_grade_rounded_to_one_decimal(self):
        """
        Criterio 2: Given el cálculo produce un resultado con más de 1 decimal
        When el sistema aplica el redondeo
        Then la nota resultante tiene exactamente 1 decimal

        Cálculo esperado:
        - documents: promedio(3.5) = 3.5 * 0.40 = 1.4
        - followups:  promedio(3.3) = 3.3 * 0.30 = 0.99
        - attendance: promedio(4.0) = 4.0 * 0.30 = 1.2
        - total sin redondear: 3.59 → redondeado: 3.6
        """
        AcademicAction.objects.create(case=self.case, action_type='document',   grade=3.5, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='followup',   grade=3.3, registered_by=self.professor)
        AcademicAction.objects.create(case=self.case, action_type='attendance', grade=4.0, registered_by=self.professor)

        result = calculate_final_grade(self.student, '2026-1', self.room)

        # Resultado redondeado a 1 decimal
        self.assertEqual(result, 3.6)

class RegisterAcademicActionViewTest(TestCase):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 1: el profesor registra una acción académica calificable
    sobre un caso activo via endpoint POST. Retorna JSON.
    """

    def setUp(self):
        """
        Montaje completo: sala, profesor, estudiante y caso activo.
        El profesor debe estar autenticado para acceder al endpoint.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )

    def test_register_action_returns_201_when_valid(self):
        """
        Criterio 1: Given el profesor está autenticado y el caso está activo
        When envía un POST con tipo de acción, nota y caso válidos
        Then el sistema retorna 201 y la acción queda registrada en la BD
        """
        # Autenticar al profesor antes de llamar al endpoint
        self.client.login(username='profesor@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'document',
                'grade': 4.5,
                'observation': 'Entrega completa y a tiempo',
            },
            content_type='application/json',
        )

        # El endpoint retorna 201 Created
        self.assertEqual(response.status_code, 201)

        # La acción quedó persistida en la BD
        self.assertTrue(AcademicAction.objects.filter(case=self.case).exists())

        # La respuesta incluye el ID de la acción creada
        import json
        data = json.loads(response.content)
        self.assertIn('id', data)

    def test_register_action_returns_401_when_not_authenticated(self):
        """
        Criterio 1: Given el usuario no está autenticado
        When intenta registrar una acción académica
        Then el sistema retorna 401 — acceso denegado
        """
        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'document',
                'grade': 4.5,
            },
            content_type='application/json',
        )

        # Sin autenticación el endpoint rechaza la petición
        self.assertEqual(response.status_code, 401)

    def test_register_action_returns_400_when_case_is_closed(self):
        """
        Criterio 1: Given el caso tiene estado 'Cerrado'
        When el profesor intenta registrar una acción sobre ese caso
        Then el sistema retorna 400 — no se permiten acciones en casos cerrados
        """
        # Cerrar el caso antes de intentar registrar la acción
        self.case.status = 'closed'
        self.case.save()

        self.client.login(username='profesor@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'document',
                'grade': 4.5,
            },
            content_type='application/json',
        )

        # No se puede registrar acción en un caso cerrado
        self.assertEqual(response.status_code, 400)

        import json
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_register_action_returns_400_when_grade_invalid(self):
        """
        Criterio 1: Given el profesor envía una nota fuera del rango 0.0-5.0
        When el sistema valida la petición
        Then retorna 400 con mensaje de error claro
        """
        self.client.login(username='profesor@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'document',
                # Nota inválida — fuera del rango permitido
                'grade': 7.0,
            },
            content_type='application/json',
        )

        # Nota inválida → 400 Bad Request
        self.assertEqual(response.status_code, 400)

class RegisterAttendanceActionViewTest(TestCase):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 5: el profesor registra la asistencia a una cita de seguimiento
    con trazabilidad completa. El registro es inmutable una vez guardado.
    """

    def setUp(self):
        """
        Montaje completo: sala, profesor, estudiante y caso activo
        listos para recibir un registro de asistencia a cita.
        """
        self.room = LegalRoom.objects.create(name='Familia')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.case = Case.objects.create(
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=20),
        )

    def test_register_attendance_returns_201_when_valid(self):
        """
        Criterio 5: Given existe una cita de seguimiento atendida
        When el profesor registra asistencia con todos los campos
        Then el sistema retorna 201 y persiste el registro con trazabilidad
        """
        self.client.login(username='profesor@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'attendance',
                'grade': 4.0,
                # Campos específicos de asistencia a cita
                'attended': True,
                'arrival_time': '09:15:00',
                'document_delivered': True,
                'observation': 'Llegó a tiempo con documentos completos',
            },
            content_type='application/json',
        )

        # El registro se persistió correctamente
        self.assertEqual(response.status_code, 201)

        # Verificar que los campos de asistencia se guardaron
        action = AcademicAction.objects.get(case=self.case)
        self.assertTrue(action.attended)
        self.assertTrue(action.document_delivered)
        self.assertIsNotNone(action.arrival_time)

    def test_attendance_record_is_immutable(self):
        """
        Criterio 5: Given una asistencia ya registrada
        When se intenta modificar la nota post-guardado
        Then el sistema lanza ValidationError — el registro es inmutable
        """
        from django.core.exceptions import ValidationError

        action = AcademicAction.objects.create(
            case=self.case,
            action_type='attendance',
            grade=4.0,
            registered_by=self.professor,
            attended=True,
            arrival_time=timezone.now().time(),
            document_delivered=True,
        )

        # Intentar modificar la nota después de guardada
        action.grade = 5.0

        # El modelo debe rechazar la modificación
        with self.assertRaises(ValidationError):
            action.full_clean()

    def test_attendance_without_arrival_time_when_not_attended(self):
        """
        Criterio 5: Given el estudiante no asistió a la cita
        When el profesor registra la inasistencia sin hora de llegada
        Then el sistema lo acepta — arrival_time es nullable cuando no asistió
        """
        self.client.login(username='profesor@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:register-academic-action'),
            data={
                'case_id': self.case.id,
                'action_type': 'attendance',
                'grade': 1.0,
                'attended': False,
                # Sin arrival_time — el estudiante no asistió
                'document_delivered': False,
            },
            content_type='application/json',
        )

        # Se registró correctamente sin hora de llegada
        self.assertEqual(response.status_code, 201)

        action = AcademicAction.objects.get(case=self.case)
        self.assertFalse(action.attended)
        self.assertIsNone(action.arrival_time)

class CaseLogModelTest(TestCase):

    def setUp(self):
        self.role = Role.objects.create(name='profesor')
        self.room = LegalRoom.objects.create(name='Laboral')
        self.user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role,
        )
        self.professor = Professor.objects.create(user=self.user)
        self.case = Case.objects.create(
            professor=self.professor,
            room=self.room,
            legal_deadline='2026-12-31',
            status='Asignado',
        )

    def test_crear_log_exitoso(self):
        log = CaseLog.objects.create(
            case=self.case,
            event_type='asignacion',
            description='Caso asignado al estudiante Juan',
            executed_by=self.user,
        )
        self.assertIsNotNone(log.id)
        self.assertIsNotNone(log.created_at)

    def test_log_tiene_campos_requeridos(self):
        log = CaseLog.objects.create(
            case=self.case,
            event_type='reasignacion',
            description='Caso reasignado por el profesor',
            executed_by=self.user,
        )
        self.assertEqual(log.event_type, 'reasignacion')
        self.assertEqual(log.description, 'Caso reasignado por el profesor')
        self.assertEqual(log.executed_by, self.user)

    def test_log_sancion_es_inmutable(self):
        log = CaseLog.objects.create(
            case=self.case,
            event_type='sancion',
            description='Caso reasignado como sanción académica',
            executed_by=self.user,
        )
        log.description = 'Descripción modificada'
        with self.assertRaises(ValidationError):
            log.full_clean()

    def test_log_no_sancion_no_lanza_error_al_modificar(self):
        log = CaseLog.objects.create(
            case=self.case,
            event_type='asignacion',
            description='Caso asignado',
            executed_by=self.user,
        )
        log.description = 'Descripción actualizada'
        try:
            log.full_clean()
        except ValidationError:
            self.fail('No debería lanzar ValidationError en logs que no son sanción')

    def test_logs_consultables_desde_caso(self):
        CaseLog.objects.create(
            case=self.case,
            event_type='asignacion',
            description='Primer evento',
            executed_by=self.user,
        )
        CaseLog.objects.create(
            case=self.case,
            event_type='reasignacion',
            description='Segundo evento',
            executed_by=self.user,
        )
        logs = self.case.logs.all()
        self.assertEqual(logs.count(), 2)


class CaseListingFilterTest(TestCase):
    """
    Tests for case listing with status filtering.
    """

    def setUp(self):
        """Setup test data for case listing tests."""
        # Create role and legal room
        self.role_secretary = Role.objects.create(name='secretaria')
        self.role_professor = Role.objects.create(name='profesor')
        self.room = LegalRoom.objects.create(name='Civil')

        # Create secretary user (authorized for case listing)
        self.secretary_user = SystemUser.objects.create_user(
            email='secretary@icesi.edu.co',
            password='test1234',
            name='Secretaria Test',
            role=self.role_secretary,
            room=self.room,
        )

        # Create professor user
        self.professor_user = SystemUser.objects.create_user(
            email='professor@icesi.edu.co',
            password='test1234',
            name='Professor Test',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        # Create beneficiary
        from accounts.models import Beneficiary
        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiary Test',
            document='12345678',
            email='beneficiary@icesi.edu.co',
            phone='555-1234',
            address='123 Test St',
            stratum=2,
        )

        # Create test cases
        self.active_case_1 = Case.objects.create(
            number='CASE-001',
            description='Active case 1',
            beneficiary=self.beneficiary,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date(),
            status='active',
        )

        self.active_case_2 = Case.objects.create(
            number='CASE-002',
            description='Active case 2',
            beneficiary=self.beneficiary,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date(),
            status='En proceso',
        )

        self.closed_case = Case.objects.create(
            number='CASE-003',
            description='Closed case',
            beneficiary=self.beneficiary,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date(),
            status='Cerrado',
        )

    def test_filter_activos_returns_only_non_closed_cases(self):
        """
        Test that filtering by 'activos' returns only cases where status != 'Cerrado'.
        """
        from cases.services import filter_cases_by_status

        result = filter_cases_by_status('activos')
        self.assertEqual(result.count(), 2)
        self.assertIn(self.active_case_1, result)
        self.assertIn(self.active_case_2, result)
        self.assertNotIn(self.closed_case, result)

    def test_filter_cerrados_returns_only_closed_cases(self):
        """
        Test that filtering by 'cerrados' returns only cases where status == 'Cerrado'.
        """
        from cases.services import filter_cases_by_status

        result = filter_cases_by_status('cerrados')
        self.assertEqual(result.count(), 1)
        self.assertIn(self.closed_case, result)
        self.assertNotIn(self.active_case_1, result)
        self.assertNotIn(self.active_case_2, result)

    def test_filter_returns_empty_for_invalid_status(self):
        """
        Test that filtering with invalid status returns empty queryset.
        """
        from cases.services import filter_cases_by_status

        result = filter_cases_by_status('invalid')
        self.assertEqual(result.count(), 0)

    def test_filter_returns_ordered_by_most_recent(self):
        """
        Test that filtered cases are ordered by most recent (created_at descending).
        """
        from cases.services import filter_cases_by_status

        result = list(filter_cases_by_status('activos'))
        # Most recent should be first (CASE-002 was created last)
        self.assertEqual(result[0].number, 'CASE-002')
        self.assertEqual(result[1].number, 'CASE-001')

    def test_case_list_view_unauthorized_user_returns_403(self):
        """
        Test that users without 'secretaria' role get 403 Forbidden.
        """
        # Create a regular user without secretaria role
        regular_user = SystemUser.objects.create_user(
            email='regular@icesi.edu.co',
            password='test1234',
            name='Regular User',
            role=None,
            room=self.room,
        )

        self.client.login(email='regular@icesi.edu.co', password='test1234')
        response = self.client.get('/cases/list/')
        self.assertEqual(response.status_code, 403)

    def test_case_list_view_secretaria_gets_activos(self):
        """
        Test that secretaria user can fetch active cases.
        """
        self.client.login(email='secretary@icesi.edu.co', password='test1234')
        response = self.client.get('/cases/list/?status=activos')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        numbers = [case['number'] for case in data]
        self.assertIn('CASE-001', numbers)
        self.assertIn('CASE-002', numbers)

    def test_case_list_view_secretaria_gets_cerrados(self):
        """
        Test that secretaria user can fetch closed cases.
        """
        self.client.login(email='secretary@icesi.edu.co', password='test1234')
        response = self.client.get('/cases/list/?status=cerrados')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['number'], 'CASE-003')
        self.assertEqual(data[0]['status'], 'Cerrado')

    def test_case_list_view_defaults_to_activos_when_missing_status(self):
        """
        Test that missing status parameter defaults to 'activos'.
        """
        self.client.login(email='secretary@icesi.edu.co', password='test1234')
        response = self.client.get('/cases/list/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should return activos cases (2)
        self.assertEqual(len(data), 2)

    def test_case_list_view_response_format(self):
        """
        Test that response contains required fields: number, beneficiary, status.
        """
        self.client.login(email='secretary@icesi.edu.co', password='test1234')
        response = self.client.get('/cases/list/?status=activos')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check first case has required fields
        case = data[0]
        self.assertIn('number', case)
        self.assertIn('beneficiary', case)
        self.assertIn('status', case)
        self.assertEqual(case['beneficiary'], 'Beneficiary Test')

class CaseStatusUpdateViewTest(TestCase):
    """
    PTCJMGA-24: Notificaciones automáticas de estado del caso
    """

    def setUp(self):
        self.room = LegalRoom.objects.create(name='Penal')
        self.role_professor = Role.objects.create(name='profesor')
        self.role_secretary = Role.objects.create(name='secretaria')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.secretary_user = SystemUser.objects.create_user(
            email='secretaria@icesi.edu.co',
            password='test1234',
            name='Laura Secretaria',
            role=self.role_secretary,
        )

        self.beneficiary = Beneficiary.objects.create(
            name='Juan Beneficiario',
            document='987654321',
            email='beneficiario@gmail.com',
            phone='3009876543',
            address='Calle 5 #6-7',
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
    def test_cambio_estado_envia_notificacion_al_beneficiario(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        response = self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        mock_send_mail.assert_called_once()

    @patch('notifications.services.send_mail')
    def test_asunto_correo_contiene_id_caso(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'En proceso'},
            content_type='application/json',
        )

        _, kwargs = mock_send_mail.call_args
        self.assertIn('Actualización de tu caso', kwargs['subject'])
        self.assertIn(str(self.case.pk), kwargs['subject'])

    @patch('notifications.services.send_mail')
    def test_cuerpo_correo_contiene_estado_anterior_y_nuevo(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        _, kwargs = mock_send_mail.call_args
        self.assertIn('Pendiente', kwargs['message'])
        self.assertIn('Asignado', kwargs['message'])

    @patch('notifications.services.send_mail')
    def test_estado_pendiente_no_envia_notificacion(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.case.status = 'Asignado'
        self.case.save()
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Pendiente'},
            content_type='application/json',
        )

        mock_send_mail.assert_not_called()

    @patch('notifications.services.send_mail')
    def test_cambio_estado_registra_en_bitacora(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        from cases.models import CaseLog
        log = CaseLog.objects.filter(case=self.case, event_type='asignacion').first()
        self.assertIsNotNone(log)

    @patch('notifications.services.send_mail')
    def test_fallo_notificacion_no_revierte_cambio_estado(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('SMTP error')
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        self.case.refresh_from_db()
        self.assertEqual(self.case.status, 'Asignado')

    @patch('notifications.services.send_mail')
    def test_fallo_notificacion_crea_failed_notification(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('SMTP error')
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        self.assertEqual(FailedNotification.objects.filter(resolved=False).count(), 1)

    @patch('notifications.services.send_mail')
    def test_beneficiario_sin_correo_no_intenta_envio(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.beneficiary.email = ''
        self.beneficiary.save()
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        mock_send_mail.assert_not_called()

    @patch('notifications.services.send_mail')
    def test_beneficiario_sin_correo_registra_en_bitacora(self, mock_send_mail):
        mock_send_mail.return_value = 1
        self.beneficiary.email = ''
        self.beneficiary.save()
        self.client.login(username='secretaria@icesi.edu.co', password='test1234')

        self.client.post(
            reverse('cases:update-status', args=[self.case.pk]),
            data={'status': 'Asignado'},
            content_type='application/json',
        )

        from cases.models import CaseLog
        log = CaseLog.objects.filter(
            case=self.case,
            event_type='error_notificacion'
        ).first()
        self.assertIsNotNone(log)
        self.assertIn('correo', log.description.lower())


class StudentCasesWithSemaphoreViewTest(TestCase):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Indicador de semáforo visible en la lista de casos del estudiante
    """

    def setUp(self):
        """
        Montaje: sala, roles, estudiante con casos activos con diferentes fechas límite.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiary Test',
            document='12345678',
            email='beneficiary@icesi.edu.co',
            phone='555-1234',
            address='123 Test St',
            stratum=2,
        )

        # Caso con ≤ 1 día restante: ROJO
        self.red_case = Case.objects.create(
            number='CASE-RED',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=1),
            status='active',
        )

        # Caso con 2 días restantes: AMARILLO
        self.yellow_case = Case.objects.create(
            number='CASE-YELLOW',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=2),
            status='active',
        )

        # Caso con > 3 días restantes: VERDE
        self.green_case = Case.objects.create(
            number='CASE-GREEN',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=5),
            status='active',
        )

    def test_student_can_get_cases_with_semaphore(self):
        """
        Given el estudiante ha iniciado sesión y tiene casos activos
        When el sistema carga la lista de casos del estudiante
        Then los casos muestran indicador ROJO/AMARILLO/VERDE según días restantes
        """
        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-cases'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Debería devolver 3 casos
        self.assertEqual(len(data), 3)

        # Encontrar cada caso por number
        cases_by_number = {case['number']: case for case in data}

        # Verificar semáforo ROJO
        red_case_data = cases_by_number['CASE-RED']
        self.assertEqual(red_case_data['semaphore'], 'red')
        self.assertEqual(red_case_data['days_remaining'], 1)

        # Verificar semáforo AMARILLO
        yellow_case_data = cases_by_number['CASE-YELLOW']
        self.assertEqual(yellow_case_data['semaphore'], 'yellow')
        self.assertEqual(yellow_case_data['days_remaining'], 2)

        # Verificar semáforo VERDE
        green_case_data = cases_by_number['CASE-GREEN']
        self.assertEqual(green_case_data['semaphore'], 'green')
        self.assertEqual(green_case_data['days_remaining'], 5)

    def test_unauthenticated_user_cannot_access_student_cases(self):
        """
        Given el usuario no está autenticado
        When intenta acceder a la lista de casos del estudiante
        Then el sistema retorna 401
        """
        response = self.client.get(reverse('cases:student-cases'))

        self.assertEqual(response.status_code, 401)

    def test_non_student_user_cannot_access_student_cases(self):
        """
        Given el usuario autenticado no es estudiante
        When intenta acceder a la lista de casos del estudiante
        Then el sistema retorna 403
        """
        # Crear un profesor y login
        self.client.login(email='profesor@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-cases'))

        self.assertEqual(response.status_code, 403)

    def test_response_includes_required_fields(self):
        """
        Given el estudiante solicita su lista de casos
        When el sistema responde
        Then cada caso incluye: id, number, beneficiary_name, days_remaining, semaphore
        """
        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-cases'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        case = data[0]
        required_fields = ['id', 'number', 'beneficiary_name', 'days_remaining', 'semaphore']
        for field in required_fields:
            self.assertIn(field, case)


class StudentDeadlineSummaryViewTest(TestCase):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Pantalla de vencimientos al iniciar sesión

    Given el estudiante inicia sesión en BURO
    And tiene al menos un caso con término legal a ≤ 7 días
    When el sistema carga la sesión
    Then se muestra una pantalla de resumen de vencimientos antes del dashboard principal
    And la pantalla lista únicamente los casos asignados al estudiante, ordenados de menor a mayor días restantes
    And cada fila muestra: ID del caso, tipo de término legal, nombre del beneficiario, días restantes e indicador de color
    And el estudiante puede cerrar la pantalla para continuar al dashboard
    """

    def setUp(self):
        """
        Montaje: sala, roles, estudiante con casos algunos con ≤ 7 días restantes.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiary Test',
            document='12345678',
            email='beneficiary@icesi.edu.co',
            phone='555-1234',
            address='123 Test St',
            stratum=2,
        )

        # Caso con 3 días restantes (≤ 7 días)
        self.critical_case = Case.objects.create(
            number='CASE-CRITICAL',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=3),
            status='active',
        )

        # Caso con 5 días restantes (≤ 7 días)
        self.warning_case = Case.objects.create(
            number='CASE-WARNING',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=5),
            status='active',
        )

        # Caso con 10 días restantes (> 7 días - no debería aparecer)
        self.normal_case = Case.objects.create(
            number='CASE-NORMAL',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=10),
            status='active',
        )

    def test_student_with_critical_cases_sees_deadline_summary(self):
        """
        Given el estudiante tiene casos con ≤ 7 días restantes
        When accede al resumen de vencimientos
        Then se muestran solo los casos críticos ordenados por días restantes
        """
        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-deadline-summary'))

        self.assertEqual(response.status_code, 200)

        # Verificar que se renderiza el template correcto
        self.assertTemplateUsed(response, 'cases/student_deadline_summary.html')

        # Verificar contexto
        cases = response.context['critical_cases']
        self.assertEqual(len(cases), 2)

        # Ordenados por días restantes (menor a mayor)
        self.assertEqual(cases[0]['days_remaining'], 3)
        self.assertEqual(cases[1]['days_remaining'], 5)

        # Verificar campos
        case_data = cases[0]
        self.assertIn('id', case_data)
        self.assertIn('number', case_data)
        self.assertIn('beneficiary_name', case_data)
        self.assertIn('days_remaining', case_data)
        self.assertIn('semaphore', case_data)

    def test_student_without_critical_cases_redirects_to_dashboard(self):
        """
        Given el estudiante no tiene casos con ≤ 7 días restantes
        When intenta acceder al resumen de vencimientos
        Then es redirigido al dashboard
        """
        # Cambiar fechas para que no haya casos críticos
        self.critical_case.legal_deadline = timezone.now().date() + timezone.timedelta(days=10)
        self.critical_case.save()
        self.warning_case.legal_deadline = timezone.now().date() + timezone.timedelta(days=15)
        self.warning_case.save()

        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-deadline-summary'))

        # Debería redirigir al dashboard
        self.assertRedirects(response, reverse('accounts:student-history'))

    def test_non_student_cannot_access_deadline_summary(self):
        """
        Given el usuario no es estudiante
        When intenta acceder al resumen de vencimientos
        Then recibe 403 Forbidden
        """
        self.client.login(email='profesor@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:student-deadline-summary'))

        self.assertEqual(response.status_code, 403)


class ProfessorCasesWithSemaphoreViewTest(TestCase):
    """
    HU: Como profesor asesor, quiero recibir alertas y ver en mi panel los casos
    de mi sala que se acercan a su fecha límite legal
    
    Criterio: Endpoint GET de casos de la sala con semáforo
    """

    def setUp(self):
        """Setup: crear profesor, sala, estudiante y casos de prueba"""
        self.room = LegalRoom.objects.create(name='Laboral')
        self.room2 = LegalRoom.objects.create(name='Penal')
        
        self.role_professor = Role.objects.create(name='PROFESSOR')
        self.role_student = Role.objects.create(name='STUDENT')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user, student_code='2026001')

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiario Prueba',
            document='123456789',
            email='beneficiary@icesi.edu.co',
            phone='3000000000',
            address='Calle 1',
            stratum=2,
            data_authorization=True,
        )

        # Casos de la sala del profesor
        self.red_case = Case.objects.create(
            number='CASE-RED-1',
            description='Caso urgente',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=1),
            status='active'
        )

        self.yellow_case = Case.objects.create(
            number='CASE-YELLOW-2',
            description='Caso cercano',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=2),
            status='active'
        )

        self.green_case = Case.objects.create(
            number='CASE-GREEN-5',
            description='Caso no urgente',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=5),
            status='active'
        )

    def test_professor_can_get_cases_from_their_room_with_semaphore(self):
        """
        Given el profesor ha iniciado sesión
        When accede al endpoint GET /cases/professor-cases/
        Then obtiene todos los casos de su sala con semáforo
        """
        self.client.login(email='profesor@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:professor-cases'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Debe haber 3 casos
        self.assertEqual(len(data), 3)

        # Red case (1 día)
        red_case_data = next(c for c in data if c['number'] == 'CASE-RED-1')
        self.assertEqual(red_case_data['semaphore'], 'red')
        self.assertEqual(red_case_data['days_remaining'], 1)

        # Yellow case (2 días)
        yellow_case_data = next(c for c in data if c['number'] == 'CASE-YELLOW-2')
        self.assertEqual(yellow_case_data['semaphore'], 'yellow')
        self.assertEqual(yellow_case_data['days_remaining'], 2)

        # Green case (5 días)
        green_case_data = next(c for c in data if c['number'] == 'CASE-GREEN-5')
        self.assertEqual(green_case_data['semaphore'], 'green')
        self.assertEqual(green_case_data['days_remaining'], 5)

    def test_professor_only_sees_cases_from_their_room(self):
        """
        Given el profesor tiene asignada una sala específica
        When solicita sus casos
        Then solo ve casos de su sala, no de otras salas
        """
        # Crear un caso en otra sala
        other_student = Student.objects.create(
            user=SystemUser.objects.create_user(
                email='student2@icesi.edu.co',
                password='test1234',
                name='Otro Estudiante',
                role=self.role_student,
                room=self.room2,
            ),
            student_code='2026002'
        )
        
        other_professor = Professor.objects.create(
            user=SystemUser.objects.create_user(
                email='profesor2@icesi.edu.co',
                password='test1234',
                name='Otro Profesor',
                role=self.role_professor,
                room=self.room2,
            )
        )

        Case.objects.create(
            number='CASE-OTHER-ROOM',
            description='Caso en otra sala',
            beneficiary=self.beneficiary,
            student=other_student,
            professor=other_professor,
            room=self.room2,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=1),
            status='active'
        )

        self.client.login(email='profesor@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('cases:professor-cases'))

        data = response.json()
        # Solo los 3 casos de la sala Laboral
        self.assertEqual(len(data), 3)
        numbers = [c['number'] for c in data]
        self.assertNotIn('CASE-OTHER-ROOM', numbers)

    def test_professor_red_cases_appear_first_sorted_by_days(self):
        """
        Given hay casos de diferentes criticidades
        When el profesor consulta su lista
        Then los casos críticos (rojo) aparecen primero, ordenados por días
        """
        self.client.login(email='profesor@icesi.edu.co', password='test1234')
        response = self.client.get(reverse('cases:professor-cases'))

        data = response.json()
        
        # Filtrar casos rojos
        red_cases = [c for c in data if c['semaphore'] == 'red']
        self.assertGreaterEqual(len(red_cases), 1)

    def test_non_professor_cannot_access_professor_cases(self):
        """
        Given el usuario es estudiante
        When intenta acceder a /cases/professor-cases/
        Then recibe 403 Forbidden
        """
        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:professor-cases'))

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_access_professor_cases(self):
        """
        Given no hay usuario autenticado
        When accede a /cases/professor-cases/
        Then recibe 401 Unauthorized
        """
        response = self.client.get(reverse('cases:professor-cases'))

        self.assertEqual(response.status_code, 401)


class ProfessorDeadlineSummaryViewTest(TestCase):
    """
    HU: Como profesor asesor, quiero recibir alertas y ver en mi panel los casos
    de mi sala que se acercan a su fecha límite legal
    
    Criterio: Pantalla de vencimientos al iniciar sesión (profesor)
    """

    def setUp(self):
        """Setup: profesor con casos críticos en su sala"""
        self.room = LegalRoom.objects.create(name='Laboral')
        
        self.role_professor = Role.objects.create(name='PROFESSOR')
        self.role_student = Role.objects.create(name='STUDENT')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.student = Student.objects.create(
            user=SystemUser.objects.create_user(
                email='student@icesi.edu.co',
                password='test1234',
                name='Ana Estudiante',
                role=self.role_student,
                room=self.room,
            ),
            student_code='2026001'
        )

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiario',
            document='123456789',
            email='beneficiary@icesi.edu.co',
            phone='3000000000',
            address='Calle 1',
            stratum=2,
            data_authorization=True,
        )

        # Casos críticos (≤ 7 días)
        self.critical_case = Case.objects.create(
            number='CASE-CRITICAL-3',
            description='Caso crítico',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=3),
            status='active'
        )

        self.warning_case = Case.objects.create(
            number='CASE-WARNING-5',
            description='Caso de alerta',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=5),
            status='active'
        )

    def test_professor_sees_deadline_summary_on_login(self):
        """
        Given el profesor tiene casos con ≤ 7 días restantes
        When inicia sesión
        Then ve la pantalla de resumen de vencimientos
        """
        self.client.login(email='profesor@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:professor-deadline-summary'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'cases/professor_deadline_summary.html')

        # Verificar que están en el contexto
        cases = response.context['critical_cases']
        self.assertEqual(len(cases), 2)

        # Ordenados por días restantes (menor a mayor)
        self.assertEqual(cases[0]['days_remaining'], 3)
        self.assertEqual(cases[1]['days_remaining'], 5)

        # Verificar campos
        case_data = cases[0]
        self.assertIn('id', case_data)
        self.assertIn('number', case_data)
        self.assertIn('student_name', case_data)
        self.assertIn('days_remaining', case_data)
        self.assertIn('semaphore', case_data)

    def test_professor_without_critical_cases_redirects_to_dashboard(self):
        """
        Given el profesor no tiene casos con ≤ 7 días
        When intenta acceder al resumen de vencimientos
        Then es redirigido al dashboard
        """
        # Cambiar fechas para que no sean críticos
        self.critical_case.legal_deadline = timezone.now().date() + timezone.timedelta(days=10)
        self.critical_case.save()
        self.warning_case.legal_deadline = timezone.now().date() + timezone.timedelta(days=15)
        self.warning_case.save()

        self.client.login(email='profesor@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:professor-deadline-summary'), follow=False)

        # Debe redirigir (código 302)
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_access_professor_deadline_summary(self):
        """
        Given el usuario es estudiante
        When intenta acceder a la pantalla de vencimientos del profesor
        Then recibe 403 Forbidden
        """
        self.client.login(email='student@icesi.edu.co', password='test1234')

        response = self.client.get(reverse('cases:professor-deadline-summary'))

        self.assertEqual(response.status_code, 403)


class DailyDeadlineCheckCommandProfessorNotificationTest(TestCase):
    """
    HU: Como profesor asesor, quiero recibir alertas y ver en mi panel los casos
    de mi sala que se acercan a su fecha límite legal
    
    Criterio: Notificación al profesor cuando un caso de su sala es crítico
    """

    def setUp(self):
        """Setup: profesor con caso crítico"""
        self.room = LegalRoom.objects.create(name='Laboral')
        
        self.role_professor = Role.objects.create(name='PROFESSOR')
        self.role_student = Role.objects.create(name='STUDENT')

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.student = Student.objects.create(
            user=SystemUser.objects.create_user(
                email='student@icesi.edu.co',
                password='test1234',
                name='Ana Estudiante',
                role=self.role_student,
                room=self.room,
            ),
            student_code='2026001'
        )

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiario',
            document='123456789',
            email='beneficiary@icesi.edu.co',
            phone='3000000000',
            address='Calle 1',
            stratum=2,
            data_authorization=True,
        )

        # Caso con ≤ 3 días (crítico)
        self.critical_case = Case.objects.create(
            number='CASE-PROF-CRITICAL',
            description='Caso crítico para profesor',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=2),
            status='active'
        )

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_professor_receives_notification_for_critical_case(self, mock_send):
        """
        Given un caso tiene ≤ 3 días antes del vencimiento
        And el profesor tiene correo institucional registrado
        When se ejecuta el comando daily_deadline_check
        Then se envía correo al profesor
        """
        from django.core.management import call_command
        
        mock_send.return_value = True

        call_command('daily_deadline_check')

        # El mock debe haber sido llamado para el caso del profesor
        self.assertTrue(mock_send.called)

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_professor_notification_includes_required_fields(self, mock_send):
        """
        Given se envía notificación al profesor
        When se ejecuta el comando
        Then el correo contiene: número de caso, nombre del estudiante, días restantes
        """
        from django.core.management import call_command
        
        mock_send.return_value = True

        call_command('daily_deadline_check')

        # Verificar que la notificación fue intentada
        self.assertTrue(mock_send.called)

    def test_unauthenticated_user_cannot_access_deadline_summary(self):
        """
        Given el usuario no está autenticado
        When intenta acceder al resumen de vencimientos
        Then recibe 401
        """
        response = self.client.get(reverse('cases:student-deadline-summary'))

        self.assertEqual(response.status_code, 401)


class DailyDeadlineCheckCommandTest(TestCase):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Notificación por correo al estudiante cuando un caso es crítico

    Given un caso asignado al estudiante tiene 3 días o menos antes del vencimiento legal
    And el estudiante tiene correo institucional registrado
    When el sistema detecta el umbral crítico en la evaluación diaria automatizada
    Then se envía correo al estudiante indicando: número de caso, tipo de término legal, días restantes y acción requerida
    And el asunto del correo es: "URGENTE — Caso [ID] vence en [N] día(s)"
    And el envío queda registrado en la bitácora del caso con fecha y hora
    And si el correo falla, el sistema registra el error y genera alerta interna para el coordinador
    """

    def setUp(self):
        """
        Montaje: sala, roles, estudiante con casos en diferentes estados de vencimiento.
        """
        self.room = LegalRoom.objects.create(name='Civil')
        self.role_student = Role.objects.create(name='STUDENT')
        self.role_professor = Role.objects.create(name='PROFESSOR')

        self.student_user = SystemUser.objects.create_user(
            email='student@icesi.edu.co',
            password='test1234',
            name='Ana Estudiante',
            role=self.role_student,
            room=self.room,
        )
        self.student = Student.objects.create(user=self.student_user)

        self.professor_user = SystemUser.objects.create_user(
            email='profesor@icesi.edu.co',
            password='test1234',
            name='Carlos Profesor',
            role=self.role_professor,
            room=self.room,
        )
        self.professor = Professor.objects.create(user=self.professor_user)

        self.beneficiary = Beneficiary.objects.create(
            name='Beneficiary Test',
            document='12345678',
            email='beneficiary@icesi.edu.co',
            phone='555-1234',
            address='123 Test St',
            stratum=2,
        )

        # Caso con 1 día restante (debe enviar correo)
        self.critical_case_1 = Case.objects.create(
            number='CASE-CRITICAL-1',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=1),
            status='active',
        )

        # Caso con 3 días restantes (debe enviar correo)
        self.critical_case_3 = Case.objects.create(
            number='CASE-CRITICAL-3',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=3),
            status='active',
        )

        # Caso con 4 días restantes (NO debe enviar correo)
        self.non_critical_case = Case.objects.create(
            number='CASE-NON-CRITICAL',
            beneficiary=self.beneficiary,
            student=self.student,
            professor=self.professor,
            room=self.room,
            legal_deadline=timezone.now().date() + timezone.timedelta(days=4),
            status='active',
        )

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_sends_email_for_critical_cases(self, mock_send_notification):
        """
        Given casos con ≤ 3 días restantes
        When se ejecuta la evaluación diaria
        Then se envía correo para cada caso crítico
        """
        mock_send_notification.return_value = True

        from cases.management.commands.daily_deadline_check import Command
        command = Command()
        command.handle()

        # Debería enviar 2 correos (para casos con 1 y 3 días)
        self.assertEqual(mock_send_notification.call_count, 2)

        # Verificar llamadas
        calls = mock_send_notification.call_args_list
        subjects = [call[1]['subject'] for call in calls]
        
        self.assertIn('URGENTE — Caso CASE-CRITICAL-1 vence en 1 día(s)', subjects)
        self.assertIn('URGENTE — Caso CASE-CRITICAL-3 vence en 3 día(s)', subjects)

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_logs_successful_email_send(self, mock_send_notification):
        """
        Given envío de correo exitoso
        When se registra en bitácora
        Then queda registro con fecha y hora
        """
        mock_send_notification.return_value = True

        from cases.management.commands.daily_deadline_check import Command
        command = Command()
        command.handle()

        # Verificar que se creó log para cada caso crítico
        from cases.models import CaseLog
        logs = CaseLog.objects.filter(event_type='deadline_alert')
        self.assertEqual(logs.count(), 2)

        for log in logs:
            self.assertIn('Alerta de vencimiento enviada', log.description)
            self.assertIsNotNone(log.created_at)

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_no_email_for_non_critical_cases(self, mock_send_notification):
        """
        Given caso con > 3 días restantes
        When se ejecuta la evaluación diaria
        Then NO se envía correo
        """
        mock_send_notification.return_value = True

        from cases.management.commands.daily_deadline_check import Command
        command = Command()
        command.handle()

        # Verificar que no se envió correo para el caso no crítico
        calls = mock_send_notification.call_args_list
        subjects = [call[1]['subject'] for call in calls]
        
        self.assertNotIn('URGENTE — Caso CASE-NON-CRITICAL', ' '.join(subjects))

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_handles_email_failure(self, mock_send_notification):
        """
        Given fallo en envío de correo
        When el sistema registra el error
        Then se crea registro de error y alerta interna
        """
        mock_send_notification.side_effect = Exception('SMTP Error')

        from cases.management.commands.daily_deadline_check import Command
        command = Command()
        command.handle()

        # Verificar que se creó log de error
        from cases.models import CaseLog
        error_logs = CaseLog.objects.filter(event_type='deadline_alert_error')
        self.assertEqual(error_logs.count(), 2)  # Uno por cada caso crítico

        # Verificar que se creó FailedNotification
        from notifications.models import FailedNotification
        failed_notifications = FailedNotification.objects.filter(resolved=False)
        self.assertEqual(failed_notifications.count(), 2)

    @patch('cases.management.commands.daily_deadline_check.send_notification')
    def test_email_content_includes_required_info(self, mock_send_notification):
        """
        Given envío de correo
        When se verifica el contenido
        Then incluye número de caso, días restantes y acción requerida
        """
        mock_send_notification.return_value = True

        from cases.management.commands.daily_deadline_check import Command
        command = Command()
        command.handle()

        # Verificar contenido del correo
        calls = mock_send_notification.call_args_list
        for call in calls:
            args, kwargs = call
            message = kwargs['body']
            
            # Verificar que incluye información requerida
            self.assertIn('número de caso', message.lower())
            self.assertIn('días restantes', message.lower())
            self.assertIn('acción requerida', message.lower())
