from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from .models import (
    SystemUser,
    Role,
    LegalRoom,
    Student,
    Professor,
    Secretary,
    Beneficiary,
    Permission,
    RolePermission,
    RoleChangeLog,
)
from cases.models import Case


class SystemUserAdminForm(forms.ModelForm):
    """Contraseña con hash al guardar (crear o cambiar)."""

    password = forms.CharField(
        label=_('Contraseña'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        required=False,
        help_text=_('Obligatoria al crear. Al editar, dejar vacío para no cambiar.'),
    )

    class Meta:
        model = SystemUser
        fields = (
            'email',
            'name',
            'document',
            'phone',
            'role',
            'room',
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
        )

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get('password'):
            raise forms.ValidationError(_('La contraseña es obligatoria para un usuario nuevo.'))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        raw = self.cleaned_data.get('password')
        if raw:
            user.set_password(raw)
        if commit:
            user.save()
            self.save_m2m()
        return user


# Formulario para crear Estudiante con usuario
class StudentCreationForm(forms.ModelForm):
    email = forms.EmailField(label=_('Correo electrónico'))
    name = forms.CharField(label=_('Nombre completo'), max_length=100)
    document = forms.CharField(label=_('Cédula'), max_length=50, required=False)
    phone = forms.CharField(label=_('Teléfono'), max_length=20, required=False)
    password = forms.CharField(
        label=_('Contraseña'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text=_('Obligatoria al crear.')
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label=_('Rol'),
        required=False,
        initial=lambda: Role.objects.filter(name='Estudiante').first()
    )
    
    class Meta:
        model = Student
        fields = ('student_code', 'semester', 'status')
    
    def save(self, commit=True):
        student = super().save(commit=False)
        with transaction.atomic():
            # Obtener o crear el rol de Estudiante
            role = self.cleaned_data.get('role')
            if not role:
                role, _ = Role.objects.get_or_create(name='Estudiante')
            
            # Crear el usuario SystemUser
            user = SystemUser.objects.create_user(
                email=self.cleaned_data['email'],
                password=self.cleaned_data['password'],
                name=self.cleaned_data['name'],
                document=self.cleaned_data['document'],
                phone=self.cleaned_data['phone'],
                role=role,
                is_active=True
            )
            student.user = user
            if commit:
                student.save()
        return student


# Formulario para crear Profesor con usuario
class ProfessorCreationForm(forms.ModelForm):
    email = forms.EmailField(label=_('Correo electrónico'))
    name = forms.CharField(label=_('Nombre completo'), max_length=100)
    document = forms.CharField(label=_('Cédula'), max_length=50, required=False)
    phone = forms.CharField(label=_('Teléfono'), max_length=20, required=False)
    password = forms.CharField(
        label=_('Contraseña'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text=_('Obligatoria al crear.')
    )
    room = forms.ModelChoiceField(
        queryset=LegalRoom.objects.all(),
        label=_('Sala jurídica'),
        required=False
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label=_('Rol'),
        required=False,
        initial=lambda: Role.objects.filter(name='Profesor').first()
    )
    
    class Meta:
        model = Professor
        fields = ('specialization',)
    
    def save(self, commit=True):
        professor = super().save(commit=False)
        with transaction.atomic():
            # Obtener o crear el rol de Profesor
            role = self.cleaned_data.get('role')
            if not role:
                role, _ = Role.objects.get_or_create(name='Profesor')
            
            room = self.cleaned_data.get('room')
            
            # Crear el usuario SystemUser
            user = SystemUser.objects.create_user(
                email=self.cleaned_data['email'],
                password=self.cleaned_data['password'],
                name=self.cleaned_data['name'],
                document=self.cleaned_data['document'],
                phone=self.cleaned_data['phone'],
                role=role,
                room=room,
                is_active=True
            )
            professor.user = user
            if commit:
                professor.save()
        return professor


# Formulario para crear Secretaria con usuario
class SecretaryCreationForm(forms.ModelForm):
    email = forms.EmailField(label=_('Correo electrónico'))
    name = forms.CharField(label=_('Nombre completo'), max_length=100)
    document = forms.CharField(label=_('Cédula'), max_length=50, required=False)
    phone = forms.CharField(label=_('Teléfono'), max_length=20, required=False)
    password = forms.CharField(
        label=_('Contraseña'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text=_('Obligatoria al crear.')
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        label=_('Rol'),
        required=False,
        initial=lambda: Role.objects.filter(name='Secretaria').first()
    )
    
    class Meta:
        model = Secretary
        fields = ()
    
    def save(self, commit=True):
        secretary = super().save(commit=False)
        with transaction.atomic():
            # Obtener o crear el rol de Secretaria
            role = self.cleaned_data.get('role')
            if not role:
                role, _ = Role.objects.get_or_create(name='Secretaria')
            
            # Crear el usuario SystemUser
            user = SystemUser.objects.create_user(
                email=self.cleaned_data['email'],
                password=self.cleaned_data['password'],
                name=self.cleaned_data['name'],
                document=self.cleaned_data['document'],
                phone=self.cleaned_data['phone'],
                role=role,
                is_active=True,
                is_staff=True  # Las secretarias suelen ser staff
            )
            secretary.user = user
            if commit:
                secretary.save()
        return secretary


@admin.register(SystemUser)
class SystemUserAdmin(admin.ModelAdmin):
    form = SystemUserAdminForm
    ordering = ('email',)
    list_display = ('email', 'name', 'role', 'room', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'role')
    search_fields = ('email', 'name', 'document')
    filter_horizontal = ('groups', 'user_permissions')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Datos personales'), {'fields': ('name', 'document', 'phone', 'role', 'room')}),
        (_('Permisos'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentCreationForm
    list_display = ('student_code', 'user', 'semester', 'status')
    search_fields = ('student_code', 'user__email', 'user__name')
    fieldsets = (
        (_('Datos del usuario'), {
            'fields': ('email', 'name', 'document', 'phone', 'password')
        }),
        (_('Información del estudiante'), {
            'fields': ('student_code', 'semester', 'status')
        }),
        (_('Configuración'), {
            'fields': ('role',),
            'classes': ('collapse',)
        }),
    )
    
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:  # Si es crear, usar el formulario personalizado
            return StudentCreationForm
        else:  # Si es editar, usar el formulario normal
            form = super().get_form(request, obj, **kwargs)
            return form


@admin.register(Secretary)
class SecretaryAdmin(admin.ModelAdmin):
    form = SecretaryCreationForm
    list_display = ('user', 'user_email')
    search_fields = ('user__email', 'user__name')
    fieldsets = (
        (_('Datos del usuario'), {
            'fields': ('email', 'name', 'document', 'phone', 'password')
        }),
        (_('Configuración'), {
            'fields': ('role',),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('Correo electrónico')
    
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:  # Si es crear, usar el formulario personalizado
            return SecretaryCreationForm
        else:  # Si es editar, usar el formulario normal
            form = super().get_form(request, obj, **kwargs)
            return form


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    form = ProfessorCreationForm
    list_display = ('user', 'specialization', 'user_email')
    search_fields = ('user__email', 'user__name', 'specialization')
    fieldsets = (
        (_('Datos del usuario'), {
            'fields': ('email', 'name', 'document', 'phone', 'password')
        }),
        (_('Información del profesor'), {
            'fields': ('specialization',)
        }),
        (_('Configuración'), {
            'fields': ('room', 'role'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = _('Correo electrónico')
    
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:  # Si es crear, usar el formulario personalizado
            return ProfessorCreationForm
        else:  # Si es editar, usar el formulario normal
            form = super().get_form(request, obj, **kwargs)
            return form


@admin.register(Case)
class RegistryCaseAdmin(admin.ModelAdmin):
    list_display = ('number', 'beneficiary', 'status', 'room', 'created_at')
    list_filter = ('status', 'room')
    search_fields = ('number', 'description', 'beneficiary__name', 'beneficiary__document')
    raw_id_fields = ('beneficiary', 'assigned_student', 'professor', 'room')


admin.site.register(Role)
admin.site.register(LegalRoom)
admin.site.register(Beneficiary)
admin.site.register(Permission)
admin.site.register(RolePermission)
admin.site.register(RoleChangeLog)
