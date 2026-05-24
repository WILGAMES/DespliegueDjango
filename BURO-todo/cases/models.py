#This is the cases/models.py file
from django.conf import settings
from django.db import models, transaction
from accounts.models import Student, Professor, LegalRoom, Beneficiary
from django.core.validators import MinValueValidator, MaxValueValidator


class Case(models.Model):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Representa un caso jurídico asignado a un estudiante dentro de una sala.
    Es la entidad central del módulo académico — las acciones calificables,
    el semáforo de vencimientos y el panel de carga todos parten de aquí.
    """

    STATUS_CHOICES = [
    ('active', 'Activo'),
    ('Pendiente', 'Pendiente'),
    ('Asignado', 'Asignado'),
    ('En proceso', 'En proceso'),
    ('Cerrado', 'Cerrado'),
]
    
    number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    description = models.TextField(blank=True, default='')
    beneficiary = models.ForeignKey(Beneficiary, on_delete=models.CASCADE, related_name='cases', null=True, blank=True)
    assigned_student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_cases')

    # FK al estudiante responsable del caso
    # si el estudiante es eliminado accidentalmente del sistema
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='assigned_cases', null=True, blank=True)

    # FK al profesor asesor
    professor = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='cases')

    # Sala jurídica a la que pertenece el caso
    room  = models.ForeignKey(LegalRoom, on_delete=models.PROTECT, related_name='cases')

    # Fecha límite legal
    legal_deadline = models.DateField()

    # Estado del caso, solo casos 'active' permiten registrar acciones académicas
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'caso'
        verbose_name = 'Case'
        verbose_name_plural = 'Cases'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.assigned_student and self.assigned_student.role:
            role_name = self.assigned_student.role.name.lower()
            if role_name not in ['student', 'estudiante']:
                raise ValidationError({'assigned_student': "El usuario asignado debe tener el rol de 'estudiante'."})

    def __str__(self):
        if self.number:
            return f'Case {self.number}'
        student_name = self.student.user.name if self.student else 'Unassigned'
        return f'Case {self.id} - {student_name}'
    
class GradeWeightConfig(models.Model):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 3 y 4: configuración de pesos porcentuales de evaluación
    definida por el profesor asesor para una sala y período específicos.
    Los tres pesos deben sumar exactamente 100%.
    """

    # Profesor que define la configuración: un profesor puede tener
    # configuraciones distintas por sala y por período
    professor  = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='grade_configs')

    # Sala jurídica a la que aplica esta configuración
    room = models.ForeignKey(LegalRoom, on_delete=models.PROTECT, related_name='grade_configs')

    # Período académico
    period     = models.CharField(max_length=20)

    # Peso porcentual para entregas de documentos
    weight_documents  = models.IntegerField()

    # Peso porcentual para seguimientos
    weight_followups  = models.IntegerField()

    # Peso porcentual para asistencias a cita
    weight_attendance = models.IntegerField()

    class Meta:
        db_table = 'configuracion_pesos'
        verbose_name = 'Grade Weight Config'
        verbose_name_plural = 'Grade Weight Configs'
        # Criterio 3: solo puede existir una configuración por profesor/sala/período
        unique_together = ('professor', 'room', 'period')

    def clean(self):
        """
        Criterio 4: valida que los tres pesos sumen exactamente 100%.
        Se ejecuta con full_clean() antes de guardar.
        """
        from django.core.exceptions import ValidationError

        total = self.weight_documents + self.weight_followups + self.weight_attendance
        if total != 100:
            raise ValidationError('Los pesos deben sumar exactamente 100%')

    def __str__(self):
        # Ejemplo: "Carlos Profesor - Laboral - 2026-1"
        return f'{self.professor.user.name} - {self.room.name} - {self.period}'
    

class AssignmentCriteriaConfig(models.Model):
    """Configuración persistente para asignación automática de casos."""

    max_cases_per_professor = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text='Número máximo de casos que puede tener asignado un profesor.'
    )
    prioritize_same_room = models.BooleanField(default=True)
    balance_workload = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'criterios_asignacion'
        verbose_name = 'Assignment Criteria Config'
        verbose_name_plural = 'Assignment Criteria Configs'
        constraints = [
            models.UniqueConstraint(
                fields=['active'],
                condition=models.Q(active=True),
                name='unique_active_assignment_criteria'
            )
        ]

    def __str__(self):
        status = 'Activo' if self.active else 'Inactivo'
        return (
            f'Configuración asignación: max {self.max_cases_per_professor} casos, '
            f'priorizar misma sala={self.prioritize_same_room}, '
            f'equilibrar carga={self.balance_workload} ({status})'
        )

ACADEMIC_ACTION_DELETE_BLOCKED_MESSAGE = (
    'Los registros académicos no pueden eliminarse. Use la opción de anulación con justificación.'
)


class AssignmentCriteriaLog(models.Model):
    """Inmutable log of changes for AssignmentCriteriaConfig.

    Each entry records a single field change, who changed it and when.
    """

    criteria = models.ForeignKey('AssignmentCriteriaConfig', on_delete=models.CASCADE, related_name='change_logs')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assignment_criteria_changes')
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bitacora_criterios_asignacion'
        verbose_name = 'Assignment Criteria Log'
        verbose_name_plural = 'Assignment Criteria Logs'
        ordering = ['-changed_at', '-id']

    def __str__(self):
        return f'Change {self.field_name} on {self.criteria_id} by {getattr(self.changed_by, "email", self.changed_by)} at {self.changed_at}'


class AutomaticAssignmentLog(models.Model):
    """Registro de cada intento de asignación automática de caso."""

    case = models.ForeignKey(
        Case,
        on_delete=models.PROTECT,
        related_name='automatic_assignment_logs',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name='automatic_assignment_logs',
        null=True,
        blank=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assignment_reason = models.TextField()
    created_by_system = models.BooleanField(default=True)

    class Meta:
        db_table = 'bitacora_asignacion_automatica'
        verbose_name = 'Automatic Assignment Log'
        verbose_name_plural = 'Automatic Assignment Logs'
        ordering = ['-assigned_at', '-id']

    def __str__(self):
        student_display = self.student.user.email if self.student else 'Sin estudiante'
        return f'AutoAssignmentLog case={self.case_id} student={student_display} at {self.assigned_at}'


class AcademicActionQuerySet(models.QuerySet):
    def delete(self, user=None):
        from django.core.exceptions import ValidationError

        logs = []
        for action in self:
            attempted_by = user or action._get_delete_attempt_user()
            logs.append(SystemLog(
                user=attempted_by,
                action_attempted='DELETE_ACADEMIC_ACTION',
                record_id=str(action.pk),
                result=SystemLog.RESULT_BLOCKED,
            ))

        if logs:
            SystemLog.objects.bulk_create(logs)

        raise ValidationError(ACADEMIC_ACTION_DELETE_BLOCKED_MESSAGE)


class AcademicActionManager(models.Manager.from_queryset(AcademicActionQuerySet)):
    pass


class AcademicAction(models.Model):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 1 y 5: representa una acción calificable registrada por el profesor
    sobre un caso activo. Los cambios de nota y observacion quedan auditados.
    Los campos de asistencia aplican únicamente cuando action_type es 'attendance'.
    """

    ACTION_TYPE_CHOICES = [
        ('document',   'Entrega de documento'),
        ('followup',   'Seguimiento'),
        ('attendance', 'Asistencia a cita'),
    ]

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_ANNULLED = 'ANNULLED'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ANNULLED, 'Annulled'),
    ]

    # Caso sobre el cual se registra la acción — debe estar activo
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='academic_actions')

    # Tipo de acción — determina qué peso aplicará en el cálculo de nota final
    action_type = models.CharField(max_length=20, choices=ACTION_TYPE_CHOICES)

    # Nota de 0.0 a 5.0 — validada en clean()
    grade = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )

    # Observación adicional del profesor — opcional
    observation = models.TextField(blank=True, default='')

    # Profesor que registró la acción — trazabilidad obligatoria
    registered_by = models.ForeignKey(Professor, on_delete=models.PROTECT, related_name='academic_actions')

    # Capturado automáticamente al momento del registro — no editable
    registered_at = models.DateTimeField(auto_now_add=True)

    # Preparado para anulacion logica futura sin eliminar el registro fisico
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    #Campos específicos de asistencia a cita (criterio 5)
    # Solo aplican cuando action_type == 'attendance', por eso son nullable

    # Si el estudiante asistió a la cita
    attended = models.BooleanField(null=True, blank=True)

    # Hora de llegada del estudiante
    arrival_time = models.TimeField(null=True, blank=True)

    # Si el estudiante entregó el documento en la cita
    document_delivered = models.BooleanField(null=True, blank=True)

    class Meta:
        db_table = 'accion_academica'
        verbose_name = 'Academic Action'
        verbose_name_plural = 'Academic Actions'

    objects = AcademicActionManager()

    def _get_traceability_changes(self):
        if not self.pk:
            return []

        try:
            original = AcademicAction.objects.get(pk=self.pk)
        except AcademicAction.DoesNotExist:
            return []

        grade_field = self._meta.get_field('grade')
        current_grade = grade_field.to_python(self.grade)

        changes = []
        if original.grade != current_grade:
            changes.append(('grade', str(original.grade), str(current_grade)))

        current_observation = self.observation or ''
        original_observation = original.observation or ''
        if original_observation != current_observation:
            changes.append(('observation', original_observation, current_observation))

        return changes

    def _get_traceability_modified_by(self, modified_by):
        if modified_by:
            return modified_by

        modified_by = getattr(self, '_modified_by', None)
        if modified_by:
            return modified_by

        if self.registered_by_id:
            return self.registered_by.user

        return None

    def _get_delete_attempt_user(self, user=None):
        if user:
            return user

        user = getattr(self, '_deleted_by', None)
        if user:
            return user

        if self.registered_by_id:
            return self.registered_by.user

        return None

    def _log_blocked_delete_attempt(self, user=None):
        SystemLog.objects.create(
            user=self._get_delete_attempt_user(user),
            action_attempted='DELETE_ACADEMIC_ACTION',
            record_id=str(self.pk),
            result=SystemLog.RESULT_BLOCKED,
        )

    def save(self, *args, **kwargs):
        modified_by = kwargs.pop('modified_by', None)
        changes = self._get_traceability_changes()
        update_fields = kwargs.get('update_fields')

        if update_fields is not None:
            update_fields = set(update_fields)
            changes = [
                change for change in changes
                if change[0] in update_fields
            ]

        with transaction.atomic():
            result = super().save(*args, **kwargs)

            if changes:
                trace_modified_by = self._get_traceability_modified_by(modified_by)
                if trace_modified_by:
                    AcademicRecordTraceability.objects.bulk_create([
                        AcademicRecordTraceability(
                            academic_action=self,
                            modified_by=trace_modified_by,
                            field_name=field_name,
                            old_value=old_value,
                            new_value=new_value,
                            event_type=AcademicRecordTraceability.EVENT_UPDATE,
                        )
                        for field_name, old_value, new_value in changes
                    ])

            return result

    def clean(self):
        """
        Criterio 1: valida rango de nota 0.0-5.0.
        """
        from django.core.exceptions import ValidationError

        # Validar rango de nota
        if self.grade is not None and not (0.0 <= float(self.grade) <= 5.0):
            raise ValidationError('La nota debe estar entre 0.0 y 5.0')

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        user = kwargs.pop('user', None)
        self._log_blocked_delete_attempt(user)
        raise ValidationError(ACADEMIC_ACTION_DELETE_BLOCKED_MESSAGE)

    def __str__(self):
        
        return f'{self.action_type} - {self.case.student.user.name} - {self.grade}'


class AcademicRecordTraceabilityQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from django.core.exceptions import ValidationError

        raise ValidationError('Los registros de trazabilidad academica son inmutables.')

    def delete(self):
        from django.core.exceptions import ValidationError

        raise ValidationError('Los registros de trazabilidad academica son inmutables.')


class AcademicRecordTraceabilityManager(models.Manager.from_queryset(AcademicRecordTraceabilityQuerySet)):
    pass


class AcademicRecordTraceability(models.Model):
    """
    Historial inmutable de cambios e intentos relevantes sobre acciones academicas.
    """

    EVENT_CREATE = 'CREATE'
    EVENT_UPDATE = 'UPDATE'
    EVENT_ANNUL_ATTEMPT = 'ANNUL_ATTEMPT'

    EVENT_TYPE_CHOICES = [
        (EVENT_CREATE, 'Create'),
        (EVENT_UPDATE, 'Update'),
        (EVENT_ANNUL_ATTEMPT, 'Annul attempt'),
    ]

    academic_action = models.ForeignKey(
        AcademicAction,
        on_delete=models.PROTECT,
        related_name='traceability_records',
    )
    modified_by = models.ForeignKey(
        'accounts.SystemUser',
        on_delete=models.PROTECT,
        related_name='academic_record_traceability',
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AcademicRecordTraceabilityManager()

    class Meta:
        db_table = 'trazabilidad_registro_academico'
        verbose_name = 'Academic Record Traceability'
        verbose_name_plural = 'Academic Record Traceabilities'
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if self.pk and AcademicRecordTraceability.objects.filter(pk=self.pk).exists():
            raise ValidationError('Los registros de trazabilidad academica son inmutables.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        raise ValidationError('Los registros de trazabilidad academica son inmutables.')

    def __str__(self):
        return f'{self.event_type} - {self.field_name} - AcademicAction {self.academic_action_id}'


class SystemLog(models.Model):
    RESULT_BLOCKED = 'BLOCKED'

    RESULT_CHOICES = [
        (RESULT_BLOCKED, 'Blocked'),
    ]

    user = models.ForeignKey(
        'accounts.SystemUser',
        on_delete=models.PROTECT,
        related_name='system_logs',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    action_attempted = models.CharField(max_length=100)
    record_id = models.CharField(max_length=100)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)

    class Meta:
        db_table = 'bitacora_sistema'
        verbose_name = 'System Log'
        verbose_name_plural = 'System Logs'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.action_attempted} - {self.record_id} - {self.result}'
    
class CaseLog(models.Model):

    EVENT_TYPE_CHOICES = [
        ('asignacion',   'Asignación'),
        ('reasignacion', 'Reasignación'),
        ('sancion',      'Sanción'),
        ('error_notificacion', 'Error de notificación'),
        ('notificacion_recordatorio', 'Notificación de recordatorio'),
    ]

    case        = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='logs')
    event_type  = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    description = models.TextField()
    executed_by = models.ForeignKey('accounts.SystemUser', on_delete=models.PROTECT, related_name='case_logs', null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'bitacora_caso'
        verbose_name = 'Case Log'
        verbose_name_plural = 'Case Logs'
        ordering = ['-created_at']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk and self.event_type == 'sancion':
            original = CaseLog.objects.get(pk=self.pk)
            if original.description != self.description:
                raise ValidationError('Los registros de sanción son inmutables.')

    def __str__(self):
        return f'{self.event_type} - Case {self.case.id} - {self.created_at}'

# cases/models.py  (agregar al final)

class Appointment(models.Model):
    """
    Representa una cita agendada para un caso jurídico.
    Solo la secretaria puede crear citas.
    """

    MODALITY_CHOICES = [
        ('presencial', 'Presencial'),
        ('telefonica', 'Telefónica'),
        ('virtual',    'Virtual'),
    ]

    STATUS_CHOICES = [
        ('programada',   'Programada'),
        ('reprogramada', 'Reprogramada'),
        ('cancelada',    'Cancelada'),
        ('completada',   'Completada'),
    ]

    case              = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='appointments')
    scheduled_datetime = models.DateTimeField()
    modality          = models.CharField(max_length=20, choices=MODALITY_CHOICES)
    # Sala física si es presencial, enlace si es virtual, número si es telefónica
    location_or_link  = models.CharField(max_length=255, blank=True)
    created_by        = models.ForeignKey('accounts.SystemUser', on_delete=models.PROTECT, related_name='created_appointments')
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='programada')
    # Previene envío duplicado de recordatorio (HU2)
    reminder_sent     = models.BooleanField(default=False)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'cita'
        verbose_name = 'Cita'
        verbose_name_plural = 'Citas'
        ordering = ['scheduled_datetime']

    def __str__(self):
        return f'Cita {self.id} — Caso {self.case.id} ({self.modality})'


class AppointmentLog(models.Model):
    """
    Bitácora de reprogramaciones de una cita.
    Cada entrada es inmutable una vez creada (HU1).
    """

    appointment       = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name='logs')
    changed_by        = models.ForeignKey('accounts.SystemUser', on_delete=models.PROTECT, related_name='appointment_changes')
    previous_datetime = models.DateTimeField()
    new_datetime      = models.DateTimeField()
    reason            = models.TextField(blank=True)
    # True cuando el motivo está vacío — facilita auditoría del profesor (HU1)
    no_reason_flag    = models.BooleanField(default=False)
    changed_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'bitacora_cita'
        verbose_name = 'Historial de Cita'
        verbose_name_plural = 'Historial de Citas'
        ordering = ['changed_at']

    def __str__(self):
        return f'Reprogramación Cita {self.appointment.id} — {self.changed_at:%Y-%m-%d}'


class CommunicationLog(models.Model):
    """
    Bitácora de correos institucionales enviados desde el sistema (HU3).
    """

    STATUS_CHOICES = [
        ('enviado', 'Enviado'),
        ('fallido', 'Fallido'),
    ]

    case       = models.ForeignKey(Case, on_delete=models.PROTECT, related_name='communications')
    sent_by    = models.ForeignKey('accounts.SystemUser', on_delete=models.PROTECT, related_name='sent_communications')
    # Lista de correos destinatarios
    recipients = models.JSONField()
    subject    = models.CharField(max_length=255)
    body       = models.TextField()
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES)
    sent_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table     = 'bitacora_comunicacion'
        verbose_name = 'Registro de Comunicación'
        verbose_name_plural = 'Registros de Comunicación'
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.subject} → {self.sent_by.name} ({self.sent_at:%Y-%m-%d})'
