#this is the accounts/models.py file
import random
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
#py manage.py makemigrations
#py manage.py migrate
#SALA_JURIDICA: Civil, Laboral, Penal, Publico, Familia
class LegalRoom(models.Model):
    #No pueden existir dos salas con el mismo nombre (Unique = true)
    name        = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        #Nombre real de la tabla en Postgresql
        db_table = 'sala_juridica'
        #Nombres para el panel de admin
        verbose_name = 'Legal Room'
        verbose_name_plural = 'Legal Rooms'

    def __str__(self):
        return self.name

#ROL: ADMIN, PROFESOR, STUDENT, SECRETARY
class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        #Nombre real de la tabla en Postgresql
        db_table = 'rol'
        #Nombres para el panel de admin
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.name

#Se creo para gestionar los usuarios por correo y no por "username" como espera Django por defecto
class SystemUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El correo es obligatorio')
        #normalize_email: convierte "JULIANAM@ICESI.EDU.CO" a "JULIANAM@icesi.edu.co"
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra_fields)
        user.set_password(password)
        #Guarda en la base de datos
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

#USUARIO_SISTEMA: estudiantes, profesores, secretarias, admin
class SystemUser(AbstractBaseUser, PermissionsMixin):
    name      = models.CharField(max_length=100)
    email     = models.EmailField(max_length=100, unique=True)
    document    = models.CharField(max_length=50, unique=True, null=True, blank=True)
    phone       = models.CharField(max_length=20, null=True, blank=True)
    role        = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name='users')
    room        = models.ForeignKey(LegalRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    otp_enabled = models.BooleanField(default=False)

    #Campos necesarios para el login
    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['name']

    objects = SystemUserManager()

    class Meta:
        db_table = 'usuario_sistema'
        verbose_name = 'System User'
        verbose_name_plural = 'System Users'

    def __str__(self):
        # f-string: "Juliana Marin (julimarin@icesi.edu.co)"
        return f'{self.name} ({self.email})'
    

#ESTUDIANTE
class Student(models.Model):
     #on_delete=CASCADE = "si borras al usuario, borra también al estudiante"
    user     = models.OneToOneField(SystemUser, on_delete=models.CASCADE, related_name='student_profile')
    semester = models.IntegerField(default=1)
    student_code  = models.CharField(max_length=7, unique=True)
    status   = models.CharField(max_length=20, default='active')

    class Meta:
        db_table = 'estudiante'
        verbose_name = 'Student'

    def get_active_cases_count(self):
        """
        Cuenta los casos académicos que todavía están activos o asignados.

        Excluye casos que ya se han cerrado, cancelado o finalizado.
        """
        excluded_statuses = ['Cerrado', 'Cancelado', 'Finalizado', 'closed', 'cancelled', 'finalizado']
        return self.assigned_cases.exclude(status__in=excluded_statuses).count()

    def __str__(self):
        return f'Student: {self.user.name}'


class Professor(models.Model):
    user           = models.OneToOneField(SystemUser, on_delete=models.CASCADE, related_name='professor_profile')
    specialization = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'profesor'
        verbose_name = 'Professor'

    def __str__(self):
        return f'Professor: {self.user.name}'
    
class Secretary(models.Model):
    user = models.OneToOneField(
        SystemUser,
        on_delete=models.CASCADE,
        related_name="secretary_profile",
    )

    class Meta:
        db_table = "secretaria"

        verbose_name = "Secretary"
        verbose_name_plural = "Secretaries"

    def __str__(self):
        return f"Secretary: {self.user.name} ({self.user.email})"

class Permission(models.Model):
    """
    Represents a specific action on a resource.
    Examples: resource='beneficiary' action='create'
              resource='case'        action='assign'
    PTCJMGA-110
    """
    resource = models.CharField(max_length=100)
    action   = models.CharField(max_length=50)

    class Meta:
        db_table        = "permission"
        unique_together = ("resource", "action")
        verbose_name    = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return f"{self.resource}:{self.action}"


class RolePermission(models.Model):
    """
    Intermediate table: relates roles with permissions.
    Allows assigning multiple permissions to a role.
    PTCJMGA-110
    """
    role       = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    class Meta:
        db_table        = "rol_permiso"
        unique_together = ("role", "permission")
        verbose_name    = "Role Permission"
        verbose_name_plural = "Role Permissions"

    def __str__(self):
        return f"{self.role.name} → {self.permission}"


class RoleChangeLog(models.Model):
    user       = models.ForeignKey(SystemUser, on_delete=models.CASCADE, related_name="role_changes")
    old_role   = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="old_role_logs")
    new_role   = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="new_role_logs")
    changed_by = models.ForeignKey(SystemUser, on_delete=models.PROTECT, related_name="role_changes_made")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bitacora_roles"
        verbose_name = "Role Change Log"
        verbose_name_plural = "Role Change Logs"

    def __str__(self):
        return f"{self.user.email}: {self.old_role.name} → {self.new_role.name} ({self.changed_at})"

class BeneficiaryManager(BaseUserManager):
    def create_user(self, document, email, password=None, **extra_fields):
        if not document:
            raise ValueError('Document (cedula) is required')
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user  = self.model(document=document, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

#Subtask: Crear modelo Beneficiario en accounts/models.py - DONE
#BENEFICIARIO
class Beneficiary(AbstractBaseUser):
    name              = models.CharField(max_length=100)
    document          = models.CharField(max_length=50, unique=True)
    email             = models.EmailField(unique=True)
    phone             = models.CharField(max_length=20)
    address           = models.TextField(max_length=100)
    date_of_birth     = models.DateField(null=True)
    #Aca hay que validar que la persona sea de un estrato vulnerable, asi que cree un rango
    #de 1-4 
    stratum           = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)])
    photo             = models.BinaryField(null=True, blank=True)
    digital_signature = models.BinaryField(null=True, blank=True)
    fingerprint_hash  = models.CharField(max_length=200, blank=True)
    data_authorization = models.BooleanField(default=False)  # Ley 1581 de 2012
    registration_date = models.DateTimeField(auto_now_add=True)
    is_active         = models.BooleanField(default=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['document', 'name']

    objects = BeneficiaryManager()

    class Meta:
        db_table = 'beneficiario'
        verbose_name = 'Beneficiary'
        verbose_name_plural = 'Beneficiaries'
        #Creamos un CheckConstraint para que ni con acceso directo a la base de datos
        #se puedan añadir un valor fuera de este rango, y evitar favores guiño guiño
        constraints = [
        models.CheckConstraint(
            check=models.Q(stratum__gte=1, stratum__lte=4),
            name='stratum_range_1_to_4'
        )
    ]

    def __str__(self):
        return f'{self.name} - {self.document}'

class DataDeletionRequest(models.Model):
    """
    Solicitud de eliminación de datos personales (Derecho al Olvido).
    PTCJMGA-XXX — Ley 1581 de 2012, Art. 8 lit. e).

    Flujo: Beneficiario crea la solicitud → estado 'Pendiente' →
    Admin/Secretaria revisa → 'Aprobada' o 'Rechazada' → si aprobada
    se ejecuta la anonimización del beneficiario y pasa a 'Ejecutada'.
    """

    STATUS_PENDIENTE  = 'Pendiente'
    STATUS_APROBADA   = 'Aprobada'
    STATUS_RECHAZADA  = 'Rechazada'
    STATUS_EJECUTADA  = 'Ejecutada'

    STATUS_CHOICES = [
        (STATUS_PENDIENTE, 'Pendiente'),
        (STATUS_APROBADA,  'Aprobada'),
        (STATUS_RECHAZADA, 'Rechazada'),
        (STATUS_EJECUTADA, 'Ejecutada'),
    ]

    # Quién pide la eliminación
    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name='deletion_requests',
    )

    # Cuándo la pidió (automático)
    requested_at = models.DateTimeField(auto_now_add=True)

    # Estado actual de la solicitud
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDIENTE,
    )

    # Motivo opcional que da el beneficiario
    reason = models.TextField(blank=True)

    # Cuándo y quién procesó (aprobó/rechazó/ejecutó) la solicitud
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        SystemUser,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='processed_deletion_requests',
    )

    # Si se rechaza, motivo del rechazo (ej: "tiene caso activo")
    rejection_reason = models.TextField(blank=True)

    class Meta:
        db_table            = 'solicitud_eliminacion'
        verbose_name        = 'Data Deletion Request'
        verbose_name_plural = 'Data Deletion Requests'
        ordering            = ['-requested_at']

    def __str__(self):
        return f'{self.beneficiary.document} → {self.status} ({self.requested_at:%Y-%m-%d})'


class OTPCode(models.Model):
    user       = models.ForeignKey(SystemUser, on_delete=models.CASCADE, related_name='otp_codes')
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used    = models.BooleanField(default=False)

    class Meta:
        db_table = 'otp_code'
        verbose_name = 'OTP Code'
        verbose_name_plural = 'OTP Codes'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.created_at + timedelta(minutes=10)

    @classmethod
    def generate(cls, user):
        code = str(random.randint(100000, 999999))
        return cls.objects.create(user=user, code=code)
  