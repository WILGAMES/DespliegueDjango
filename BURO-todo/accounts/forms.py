from django import forms
from django.contrib.auth import authenticate

from .models import Beneficiary, SystemUser, Student, Role, LegalRoom, Secretary, Professor
from cases.models import Case
from django.core.exceptions import ValidationError

TAILWIND_INPUT = (
    'w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 '
    'text-white placeholder-gray-500 '
    'focus:ring-2 focus:ring-blue-500 focus:border-transparent '
    'transition-all duration-200 outline-none'
)
TAILWIND_SELECT = TAILWIND_INPUT + ' appearance-none bg-white'
TAILWIND_CHECKBOX = 'h-4 w-4 text-blue-600 rounded border-gray-300'

# Light-theme inputs para vistas del dashboard (fondo blanco)
LIGHT_INPUT = (
    'w-full px-4 py-3 rounded-xl bg-white border border-gray-300 '
    'text-slate-800 placeholder-slate-400 '
    'focus:ring-2 focus:border-[#5454E9] focus:outline-none '
    'transition-all duration-200'
)
LIGHT_SELECT = (
    'w-full px-4 py-3 rounded-xl bg-white border border-gray-300 '
    'text-slate-800 appearance-none '
    'focus:ring-2 focus:border-[#5454E9] focus:outline-none '
    'transition-all duration-200'
)

class CaseCreationForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = ['number', 'description', 'beneficiary', 'assigned_student', 'professor', 'room', 'legal_deadline']
        widgets = {
            'number': forms.TextInput(attrs={'class': LIGHT_INPUT, 'placeholder': 'Ej. IC-1456'}),
            'description': forms.Textarea(attrs={'class': LIGHT_INPUT, 'rows': 3, 'placeholder': 'Describe brevemente el caso...'}),
            'beneficiary': forms.Select(attrs={'class': LIGHT_SELECT}),
            'assigned_student': forms.Select(attrs={'class': LIGHT_SELECT}),
            'professor': forms.Select(attrs={'class': LIGHT_SELECT}),
            'room': forms.Select(attrs={'class': LIGHT_SELECT}),
            'legal_deadline': forms.DateInput(attrs={'class': LIGHT_INPUT, 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar solo usuarios que tengan el rol de estudiante
        self.fields['assigned_student'].queryset = SystemUser.objects.filter(
            role__name__in=['student', 'estudiante']
        )

class AcademicHistoryFilterForm(forms.Form):
    year = forms.IntegerField(
        label='Año',
        required=False,
        widget=forms.NumberInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': '2026',
        }),
    )
    room = forms.CharField(
        label='Sala jurídica',
        required=False,
        widget=forms.TextInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': 'Civil, Laboral, Penal...',
        }),
    )

class BeneficiaryRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': '••••••••',
        }),
    )
    password2 = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': '••••••••',
        }),
    )
    data_authorization = forms.BooleanField(
        label='Acepto el tratamiento de datos personales (Ley 1581 de 2012)',
        required=True,
        widget=forms.CheckboxInput(attrs={'class': TAILWIND_CHECKBOX}),
    )

    class Meta:
        model = Beneficiary
        fields = [
            'name', 'document', 'email', 'phone',
            'address', 'date_of_birth', 'stratum',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Nombre completo'}),
            'document': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Número de documento'}),
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'correo@ejemplo.com'}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '300 123 4567'}),
            'address': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Dirección'}),
            'date_of_birth': forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}),
            'stratum': forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '1-4'}),
        }
        error_messages = {
            'name': {
                'required': 'El nombre es obligatorio.',
                'max_length': 'El nombre no puede superar los 100 caracteres.',
            },
            'document': {
                'required': 'El documento es obligatorio.',
                'unique': 'El usuario con ese documento ya se encuentra registrado.',
            },
            'email': {
                'required': 'El correo es obligatorio.',
                'invalid': 'Ingrese un correo electrónico válido.',
                'unique': 'El usuario con ese correo ya se encuentra registrado.',
            },
            'phone': {
                'required': 'El teléfono es obligatorio.',
            },
            'address': {
                'required': 'La dirección es obligatoria.',
            },
            'stratum': {
                'required': 'El estrato es obligatorio.',
                'min_value': 'El estrato debe estar entre 1 y 4.',
                'max_value': 'El estrato debe estar entre 1 y 4.',
            },
        }

    def clean_data_authorization(self):
        acept = self.cleaned_data.get('data_authorization')
        if not acept:
            raise forms.ValidationError('Es obligatorio aceptar el tratamiento de datos personales para continuar.')
        return acept

    def clean_document(self):
        document = self.cleaned_data.get('document')
        if Beneficiary.objects.filter(document=document).exists():
            raise forms.ValidationError('El usuario con ese documento ya se encuentra registrado.')
        return document

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Beneficiary.objects.filter(email=email).exists():
            raise forms.ValidationError('El usuario con ese correo ya se encuentra registrado.')
        return email

    def clean_date_of_birth(self):
        from datetime import date
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                raise forms.ValidationError('El beneficiario debe ser mayor de edad (18 años).')
        return dob

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Contraseñas no coinciden.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.data_authorization = self.cleaned_data['data_authorization']
        if commit:
            user.save()
        return user

class BeneficiaryLoginForm(forms.Form):
    username = forms.CharField(label='Numero de documento o correo', widget=forms.EmailInput(attrs={'class': TAILWIND_INPUT,'placeholder': 'ID o correo'}))
    password = forms.CharField(label='Contraseña', widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT,'placeholder': '••••••••'}))

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get('username')
        password = cleaned.get('password')
        if username and password:
            self.user_cache = authenticate(
                request=None,
                username=username,
                password=password
            )
            if self.user_cache is None:
                raise forms.ValidationError('Credenciales invalidas. Verifica tu usuario y contraseña.')
        return cleaned

    def get_user(self):
        return self.user_cache

# TODO: Chicos Este form es de LOGIN, no de registro de estudiante...
# Moverlo a una clase separada (ej: StudentLoginForm) cuando se implemente el login.
# Se reemplazó por StudentRegistrationForm para el registro.
# — Juliana

#class StudentRegistrationForm(forms.ModelForm):
#    username = forms.CharField(label='Numero de documento o correo', widget=forms.EmailInput(attrs={'class': TAILWIND_INPUT,'placeholder': 'ID o correo'}))
#    password = forms.CharField(label='Contraseña', widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT,'placeholder': '••••••••'}))
#    def clean(self):
#        cleaned = super().clean()
#        username = cleaned.get('username')
#        password = cleaned.get('password')
#        if username and password:
#            self.user_cache = authenticate(
#               request=None,
#                username=username,
#                password=password
#            )
#            if self.user_cache is None:
#                raise forms.ValidationError('Invalid credentials. Please try again.')
#        return cleaned

#    def get_user(self):
#        return self.

class StudentRegistrationForm(forms.ModelForm):
    student_code = forms.CharField(max_length=7, min_length=7, widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: 2012345'}),)
    semester = forms.IntegerField(min_value=1, max_value=12, widget=forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '1-12'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}))

    class Meta:
        model = SystemUser
        fields = ['name', 'email', 'document', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Nombre completo'}),
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'correo@icesi.edu.co'}),
            'document': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Número de documento'}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: +573001234567'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        role_student, _ = Role.objects.get_or_create(name='student')
        user.role = role_student
        if commit:
            user.save()
            Student.objects.create(
                user=user,
                student_code=self.cleaned_data['student_code'],
                semester=self.cleaned_data['semester'],
            )
        return user

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email.endswith('@icesi.edu.co'):
            raise forms.ValidationError('Debe usar su correo institucional ICESI (@icesi.edu.co).')
        if SystemUser.objects.filter(email=email).exists():
            raise forms.ValidationError('Este correo ya está registrado.')
        return email
    def clean_student_code(self):
        code = self.cleaned_data.get('student_code')
        if Student.objects.filter(student_code=code).exists():
            raise forms.ValidationError('Este código estudiantil ya está registrado.')
        return code

    
class secretaryRegistrationForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        label="Nombre completo",
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: Ana María López'}),
    )
    email = forms.EmailField(
        label="Correo institucional",
        widget=forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'correo@icesi.edu.co'}),
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        label="Teléfono celular",
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: +573001234567'}),
    )
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}),
        min_length=8,
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}),
    )
    room = forms.ModelChoiceField(
        queryset=LegalRoom.objects.all(),
        label="Sala jurídica",
        empty_label="-- Seleccionar sala --",
        widget=forms.Select(attrs={'class': TAILWIND_INPUT}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not LegalRoom.objects.exists():
            LegalRoom.objects.bulk_create([
                LegalRoom(name='Civil', description='Sala civil'),
                LegalRoom(name='Laboral', description='Sala laboral'),
                LegalRoom(name='Penal', description='Sala penal'),
                LegalRoom(name='Público', description='Sala pública'),
                LegalRoom(name='Familia', description='Sala de familia'),
            ])
        self.fields['room'].queryset = LegalRoom.objects.all()

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower()
        if not email.endswith("@icesi.edu.co"):
            raise ValidationError("Debe usar su correo institucional (@icesi.edu.co).")
        if SystemUser.objects.filter(email=email).exists():
            raise ValidationError("Este correo ya está registrado.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        role_secretary, _ = Role.objects.get_or_create(name="secretaria")
        user = SystemUser.objects.create_user(
            email=data["email"],
            name=data["name"],
            password=data["password1"],
            role=role_secretary,
            room=data["room"],
            phone=data.get("phone") or None,
        )
        return Secretary.objects.create(user=user)

class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        label='Código de verificación',
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': '123456',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
        }),
    )


class ProfessorRegistrationForm(forms.ModelForm):
    specialization = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: Derecho Penal'}),
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}),
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '••••••••'}),
    )

    class Meta:
        model = SystemUser
        fields = ['name', 'email', 'document', 'phone']
        widgets = {
            'name': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Nombre completo'}),
            'email': forms.EmailInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'correo@icesi.edu.co'}),
            'document': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Número de documento'}),
            'phone': forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Ej: +573001234567'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cleaned

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email.endswith('@icesi.edu.co'):
            raise forms.ValidationError('Debe usar su correo institucional ICESI (@icesi.edu.co).')
        if SystemUser.objects.filter(email=email).exists():
            raise forms.ValidationError('Este correo ya está registrado.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        role_professor, _ = Role.objects.get_or_create(name='professor')
        user.role = role_professor
        if commit:
            user.save()
            Professor.objects.create(
                user=user,
                specialization=self.cleaned_data['specialization'],
            )
        return user

# ============================================================
# PTCJMGA-55: Derecho al Olvido (Eliminación de Datos)
# ============================================================

from .models import DataDeletionRequest


class DataDeletionRequestForm(forms.ModelForm):
    """
    Formulario para que un beneficiario solicite la eliminación de sus datos.
    PTCJMGA-55 — Ley 1581 de 2012, Art. 8 lit. e).

    Solo expone el campo 'reason' (motivo opcional). El beneficiario y
    el estado se asignan en la vista.
    """

    class Meta:
        model  = DataDeletionRequest
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Cuéntanos por qué solicitas la eliminación (opcional)',
                'class': 'w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 '
                         'text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 '
                         'focus:border-transparent transition-all duration-200 outline-none',
            }),
        }
        labels = {
            'reason': 'Motivo de la solicitud',
        }
        help_texts = {
            'reason': 'Este campo es opcional. La información ayuda al equipo administrativo '
                      'a entender mejor su caso.',
        }