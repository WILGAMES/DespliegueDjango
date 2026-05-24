from django.shortcuts import render, redirect
from django.utils import timezone
from .utils import (
    auto_assign_cases,
    get_academic_dashboard,
    validate_professor,
    validate_coordinator,
    get_student_load,
    get_global_metrics,
    get_student_metrics,
    get_user_role,
    normalize_role_name,
    get_system_statistics,
    
)
from django.views.generic import TemplateView, FormView
from django.urls import reverse_lazy
from .forms import DataDeletionRequestForm
from .models import DataDeletionRequest
from django.contrib.auth import login, logout
from django.contrib import messages
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.conf import settings
from twilio.rest import Client as TwilioClient
from .models import Beneficiary, Student, LegalRoom, SystemUser, OTPCode
from cases.models import Case as RegistryCase, Case as AcademicCase
from .forms import (
    BeneficiaryRegistrationForm,
    BeneficiaryLoginForm,
    CaseCreationForm,
    AcademicHistoryFilterForm,
    StudentRegistrationForm,
    ProfessorRegistrationForm,
    secretaryRegistrationForm,
    OTPVerifyForm,
)
from django.http import HttpResponse, JsonResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from datetime import datetime
from django.contrib.auth.decorators import login_required


class DashboardView(View):
    def get(self, request):
        role_name = normalize_role_name(get_user_role(request.user))
        cards = []
        quick_actions = []
        
        # Todos los casos no cerrados (activos, pendientes, en proceso, asignados)
        active_count  = RegistryCase.objects.exclude(status='Cerrado').count()
        pending_count = RegistryCase.objects.filter(status='Pendiente').count()
        closed_count  = RegistryCase.objects.filter(status='Cerrado').count()

        if request.user.is_authenticated and (role_name.lower() in ['secretary', 'secretaria'] or getattr(request.user, 'secretary_profile', None) is not None):
            cards = [
                {'label': 'Casos activos', 'value': str(active_count), 'link': '/accounts/cases/'},
                {'label': 'Pendientes', 'value': str(pending_count), 'link': '/accounts/cases/'},
                {'label': 'Cerrados', 'value': str(closed_count), 'link': '/accounts/cases/?status=cerrados'},
                {'label': 'Registrar nuevo', 'value': 'Crear', 'link': '/accounts/cases/new/'},
            ]
            quick_actions = [
                {'title': 'Crear estudiante', 'description': 'Registra un nuevo estudiante en el sistema académico.', 'link': '/accounts/register/student/', 'icon': '👤'},
                {'title': 'Crear profesor', 'description': 'Registra un nuevo profesor en el sistema académico.', 'link': '/accounts/register/professor/', 'icon': '🎓'},
                {'title': 'Crear secretaria', 'description': 'Registra una nueva secretaria administrativo.', 'link': '/accounts/secretary/register/', 'icon': '📋'},
                {'title': 'Registrar caso nuevo', 'description': 'Crea un caso con datos del beneficiario y estado inicial.', 'link': '/accounts/cases/new/', 'icon': '📁'},
                {'title': 'Ver casos', 'description': 'Consulta la lista de casos registrados y su estado.', 'link': '/accounts/cases/', 'icon': '📊'},
                {'title': 'Estadísticas del sistema', 'description': 'Genera indicadores globales del rendimiento académico.', 'link': '/accounts/secretary/statistics/', 'icon': '📈'},
            ]
        elif role_name.lower() in ['student', 'estudiante']:
            cards = [
                {'label': 'Historial académico', 'value': '10 registros', 'link': '/accounts/student/history/'},
                {'label': 'Filtrar por año', 'value': 'UI listo', 'link': '/accounts/student/history/'},
            ]
            quick_actions = [
                {'title': 'Revisar historial', 'description': 'Consulta tus notas, docentes y estado de cada periodo.', 'link': '/accounts/student/history/'},
            ]
        elif role_name.lower() in ['beneficiary', 'beneficiario']:
            beneficiary = request.user if isinstance(request.user, Beneficiary) else None
            if beneficiary is None:
                try:
                    beneficiary = Beneficiary.objects.get(email=request.user.email)
                except Beneficiary.DoesNotExist:
                    beneficiary = None

            if beneficiary:
                ben_cases = RegistryCase.objects.filter(beneficiary=beneficiary).order_by('-created_at')
                ben_active = ben_cases.exclude(status='Cerrado').count()
                last_case = ben_cases.first()
                last_status = last_case.status if last_case else 'Sin casos'
            else:
                ben_active = 0
                last_status = 'Sin casos'

            cards = [
                {'label': 'Casos activos', 'value': str(ben_active), 'link': '/accounts/beneficiary/cases/'},
                {'label': 'Último estado', 'value': last_status, 'link': '/accounts/beneficiary/cases/'},
            ]
            quick_actions = [
                {'title': 'Ver estado del caso', 'description': 'Consulta el estado actual de tus casos asignados.', 'link': '/accounts/beneficiary/cases/'},
            ]
        elif role_name.lower() in ['profesor', 'professor']:
            cards = [
                {'label': 'Gestión académica', 'value': 'Ver', 'link': '/accounts/professor/load/'},
                {'label': 'Métricas', 'value': 'Ver', 'link': '/accounts/professor/metrics/'},
            ]
            quick_actions = [
                # Backend existente: formulario completo de calificación en register_academic_action.html
                {'title': 'Calificar estudiante', 'description': 'Registra notas y observaciones académicas para tus estudiantes.', 'link': '/cases/professor-students-for-grading/'},
                {'title': 'Supervisar carga académica', 'description': 'Consulta carga por estudiante y ejecuta asignación automática.', 'link': '/accounts/professor/load/'},
                {'title': 'Revisar resultados de asignación', 'description': 'Visualiza qué casos fueron asignados y a quién.', 'link': '/accounts/professor/auto-assign/results/'},
            ]
        else:
            cards = [
                {'label': 'Bienvenido', 'value': 'Selecciona un rol', 'link': '/accounts/'},
            ]
            quick_actions = [
                {'title': 'Solicita acceso', 'description': 'Pide a la administración que asigne tu rol correcto.', 'link': '/accounts/'},
            ]

        context = {
            'page_title': 'Tablero',
            'role_name': role_name,
            'user_name': getattr(request.user, 'name', request.user.email if hasattr(request.user, 'email') else 'Usuario'),
            'cards': cards,
            'quick_actions': quick_actions,
        }
        return render(request, 'accounts/dashboard_home.html', context)

def _send_otp_sms(phone: str, code: str) -> None:
    client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=f'Tu código de verificación del Consultorio Jurídico ICESI es: {code}. Expira en 10 minutos.',
        from_=settings.TWILIO_SENDER,
        to=phone,
    )


class LoginView(View):
    def get(self, request):
        form = BeneficiaryLoginForm()
        return render(request, 'accounts/login.html', {'form': form})

    def post(self, request):
        form = BeneficiaryLoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()

            if isinstance(user, SystemUser) and user.otp_enabled:
                if not user.phone:
                    messages.error(request, 'Tu cuenta tiene 2FA habilitado pero no tiene número de teléfono registrado. Contacta al administrador.')
                    return render(request, 'accounts/login.html', {'form': form})

                otp = OTPCode.generate(user)
                try:
                    _send_otp_sms(user.phone, otp.code)
                except Exception:
                    messages.error(request, 'No se pudo enviar el SMS de verificación. Intenta de nuevo.')
                    otp.delete()
                    return render(request, 'accounts/login.html', {'form': form})

                request.session['_2fa_user_id'] = user.pk
                request.session['_2fa_backend'] = user.backend
                return redirect('accounts:otp-verify')

            login(request, user)
            messages.success(request, f"Bienvenido, {user.name}")
            role_name = normalize_role_name(get_user_role(user))
            
            if role_name == 'estudiante':
                # Verificar si el estudiante tiene casos críticos (≤ 7 días)
                try:
                    student = user.student_profile
                    today = timezone.now().date()
                    critical_cases_count = RegistryCase.objects.filter(
                        student=student,
                        status='active',
                        legal_deadline__lte=today + timezone.timedelta(days=7)
                    ).count()
                    
                    if critical_cases_count > 0:
                        return redirect('cases:student-deadline-summary')
                except Student.DoesNotExist:
                    pass  # Si no tiene perfil de estudiante, continuar normal
                
                return redirect('accounts:student-dashboard')
            
            role_redirect_map = {
                'beneficiario': 'accounts:beneficiary-dashboard',
                'estudiante': 'accounts:student-dashboard',
                'profesor': 'accounts:professor-dashboard',
                'secretaria': 'accounts:secretary-dashboard',
            }
            return redirect(role_redirect_map.get(role_name, 'accounts:dashboard'))
        return render(request, 'accounts/login.html', {'form': form})


class OTPVerifyView(View):
    def get(self, request):
        if '_2fa_user_id' not in request.session:
            return redirect('accounts:login')
        return render(request, 'accounts/otp_verify.html', {'form': OTPVerifyForm()})

    def post(self, request):
        if '_2fa_user_id' not in request.session:
            return redirect('accounts:login')

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            user_id = request.session['_2fa_user_id']
            backend  = request.session['_2fa_backend']
            code     = form.cleaned_data['code']

            try:
                user = SystemUser.objects.get(pk=user_id)
                otp  = user.otp_codes.filter(code=code, is_used=False).latest('created_at')
            except (SystemUser.DoesNotExist, OTPCode.DoesNotExist):
                messages.error(request, 'Código inválido. Verifica e intenta de nuevo.')
                return render(request, 'accounts/otp_verify.html', {'form': form})

            if not otp.is_valid():
                messages.error(request, 'El código ha expirado. Por favor inicia sesión de nuevo.')
                del request.session['_2fa_user_id']
                del request.session['_2fa_backend']
                return redirect('accounts:login')

            otp.is_used = True
            otp.save()
            del request.session['_2fa_user_id']
            del request.session['_2fa_backend']
            user.backend = backend
            login(request, user)
            messages.success(request, f"Bienvenido, {user.name}")
            return redirect('accounts:dashboard')

        return render(request, 'accounts/otp_verify.html', {'form': form})

class LogoutView(View):
    def get(self, request):
        logout(request)

        messages.success(request, 'Has cerrado sesión correctamente')

        return redirect('accounts:login')

class CaseCreateView(LoginRequiredMixin, View):
    def get(self, request):
        role_name = get_user_role(request.user)
        if not request.user.is_staff and role_name.lower() not in ['secretary', 'secretaria']:
            messages.error(request, 'Acceso denegado. Solo la secretaria puede registrar casos.')
            return redirect('accounts:dashboard')

        return render(request, 'accounts/case_create.html', {
            'page_title': 'Registrar caso',
            'role_name': role_name,
            'form': CaseCreationForm(),
        })

    def post(self, request):
        role_name = get_user_role(request.user)
        if not request.user.is_staff and role_name.lower() not in ['secretary', 'secretaria']:
            messages.error(request, 'Acceso denegado. Solo la secretaria puede crear casos.')
            return redirect('accounts:dashboard')

        form = CaseCreationForm(request.POST)
        if form.is_valid():
            case = form.save(commit=False)
            case.status = 'Pendiente'
            case.save()
            messages.success(request, 'Caso registrado correctamente. Estado inicial: Pendiente.')
            return redirect('accounts:case-list')

        return render(request, 'accounts/case_create.html', {
            'page_title': 'Registrar caso',
            'role_name': role_name,
            'form': form,
        })

class CaseListView(LoginRequiredMixin, View):
    def get(self, request):
        role_name = get_user_role(request.user)
        if not request.user.is_staff and role_name.lower() not in ['secretary', 'secretaria']:
            messages.error(request, 'Acceso denegado. Solo la secretaria puede ver la lista de casos.')
            return redirect('accounts:dashboard')

        cases = RegistryCase.objects.select_related('beneficiary', 'room').order_by('-created_at')

        return render(request, 'accounts/case_list.html', {
            'page_title': 'Casos registrados',
            'role_name': role_name,
            'cases': cases,
        })

class BeneficiaryCaseStatusView(LoginRequiredMixin, View):
    def get(self, request):
        role_name = get_user_role(request.user)
        if role_name.lower() not in ['beneficiary', 'beneficiario']:
            messages.error(request, 'Acceso denegado. Solo el beneficiario puede consultar el estado de su caso.')
            return redirect('accounts:dashboard')

        beneficiary = request.user if isinstance(request.user, Beneficiary) else None
        if beneficiary is None:
            try:
                beneficiary = Beneficiary.objects.get(email=request.user.email)
            except Beneficiary.DoesNotExist:
                messages.error(request, 'No se encontró un perfil de beneficiario asociado a esta cuenta.')
                return redirect('accounts:dashboard')

        beneficiary_cases = RegistryCase.objects.filter(beneficiary=beneficiary).select_related('room').order_by('-created_at')

        return render(request, 'accounts/beneficiary_cases.html', {
            'page_title': 'Mis casos',
            'role_name': role_name,
            'beneficiary_cases': beneficiary_cases,
        })

class StudentAcademicHistoryView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return get_user_role(self.request.user).lower() == 'student' or get_user_role(self.request.user).lower() == 'estudiante'

    def handle_no_permission(self):
        messages.error(self.request, 'Acceso denegado. Solo el estudiante puede ver su historial académico.')
        return redirect('accounts:dashboard')

    def get(self, request):
        role_name = get_user_role(request.user)
        # Asegurarse de que el usuario logueado es un SystemUser y tiene un perfil de Student
        if not hasattr(request.user, 'student_profile'):
            messages.error(request, 'No se encontró un perfil de estudiante asociado a este usuario.')
            return redirect('accounts:dashboard')

        student_profile = request.user.student_profile
        
        assigned_cases = request.user.assigned_cases.select_related('professor__user', 'room')

        filter_form = AcademicHistoryFilterForm(request.GET or None)
        if filter_form.is_valid():
            year = filter_form.cleaned_data.get('year')
            room = filter_form.cleaned_data.get('room')
            if year:
                assigned_cases = assigned_cases.filter(created_at__year=year)
            if room:
                assigned_cases = assigned_cases.filter(room__name__icontains=room)

        history_records = []
        for case in assigned_cases.order_by('-created_at'):
            grade = 'Por calificar'
            if case.status.lower() in ['finalizado', 'aprobado']:
                grade = 'Aprobado'
            elif case.status.lower() in ['reprobado', 'no aprobado']:
                grade = 'Reprobado'

            history_records.append({
                'number': getattr(case, 'number', None) or f'CASO-{case.pk}',
                'period': case.created_at.strftime('%Y-%m'),
                'grade': grade,
                'professor': case.professor.user.name if case.professor else 'N/A',
                'status': case.status,
                'room': case.room.name if case.room else 'N/A',
            })

        return render(request, 'accounts/student_history.html', {
            'page_title': 'Historial académico',
            'role_name': role_name,
            'filter_form': filter_form,
            'history_records': history_records,
        })

class StudentHistoryPDFView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return get_user_role(self.request.user).lower() == 'student' or get_user_role(self.request.user).lower() == 'estudiante'

    def handle_no_permission(self):
        messages.error(self.request, 'Acceso denegado. Solo el estudiante puede exportar su historial académico.')
        return redirect('accounts:dashboard')

    def get(self, request):
        student_profile = request.user.student_profile
        assigned_cases = request.user.assigned_cases.select_related('professor__user', 'room')

        filter_form = AcademicHistoryFilterForm(request.GET or None)
        if filter_form.is_valid():
            year = filter_form.cleaned_data.get('year')
            room = filter_form.cleaned_data.get('room')
            if year:
                assigned_cases = assigned_cases.filter(created_at__year=year)
            if room:
                assigned_cases = assigned_cases.filter(room__name__icontains=room)

        history_records = []
        for case in assigned_cases.order_by('-created_at'):
            grade = 'Por calificar'
            if case.status.lower() in ['finalizado', 'aprobado']:
                grade = 'Aprobado'
            elif case.status.lower() in ['reprobado', 'no aprobado']:
                grade = 'Reprobado'

            history_records.append({
                'number': getattr(case, 'number', None) or f'CASO-{case.pk}',
                'period': case.created_at.strftime('%Y-%m'),
                'grade': grade,
                'professor': case.professor.user.name if case.professor else 'N/A',
                'status': case.status,
                'room': case.room.name if case.room else 'N/A',
            })

        # Generar PDF
        response = HttpResponse(content_type='application/pdf')
        filename = f"Historial_{student_profile.student_code}_{datetime.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        doc = SimpleDocTemplate(response, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Título
        title = Paragraph("Historial Académico - Consultorio Jurídico", styles['Title'])
        story.append(title)
        story.append(Spacer(1, 12))

        # Información del estudiante
        student_info = f"""
        <b>Estudiante:</b> {request.user.name}<br/>
        <b>Código Estudiantil:</b> {student_profile.student_code}<br/>
        <b>Fecha de Generación:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>
        """
        story.append(Paragraph(student_info, styles['Normal']))
        story.append(Spacer(1, 12))

        # Tabla de historial
        data = [['Período', 'Nota', 'Docente Supervisor', 'Estado de Aprobación', 'Sala Jurídica']]
        for record in history_records:
            data.append([record['period'], record['grade'], record['professor'], record['status'], record['room']])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

        # Firma digital
        signature = Paragraph("<b>Firmado digitalmente por Universidad ICESI</b><br/>Sello Institucional", styles['Normal'])
        story.append(signature)

        doc.build(story)
        return response
class RegisterStudentView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied('El registro de usuarios internos solo se realiza por administracion.')
        form = StudentRegistrationForm()
        return render(request, 'accounts/register_student.html', {'form': form})
    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied('El registro de usuarios internos solo se realiza por administracion.')
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            student = form.save()
            messages.success(request, f'Estudiante {student.name} registrado exitosamente. Documento: {student.document}')
            return redirect('accounts:login')
        return render(request, 'accounts/register_student.html', {'form': form})
        
class RegisterBeneficiaryView(View):
    
    def get(self, request):
        form = BeneficiaryRegistrationForm()
        return render(request, 'accounts/register_beneficiary.html', {'form': form})

    def post(self, request):
        requested_role = request.POST.get('role')
        if requested_role and normalize_role_name(requested_role) != 'beneficiario':
            raise PermissionDenied('El registro publico solo permite crear beneficiarios.')
        form = BeneficiaryRegistrationForm(request.POST)
        if form.is_valid():
            beneficiary = form.save()
            messages.success(
                request,
                f'Beneficiario {beneficiary.name} registrado exitosamente. Documento: {beneficiary.document}'
            )

            return redirect('accounts:login')

        return render(request, 'accounts/register_beneficiary.html', {'form': form})
    

def solo_secretary(view_func):
    """
    Decorator: only allows access to users with role.name == 'secretary' or 'secretaria',
    or Django superusers.
    PTCJMGA-108
    """
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/accounts/login/")
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        try:
            rol = request.user.role.name
        except AttributeError:
            rol = None
        if rol not in ("secretaria", "secretary"):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


@solo_secretary
def register_secretaria(request):
    if not request.user.is_staff:
        raise PermissionDenied
    if request.method == "POST":
        form = secretaryRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("accounts:login")
    else:
        form = secretaryRegistrationForm()
    return render(request, "accounts/register_secretary.html", {"form": form})


def secretaria_success(request):
    return render(request, "accounts/secretary_success.html")

class RegisterProfessorView(View):
    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied('El registro de usuarios internos solo se realiza por administracion.')
        form = ProfessorRegistrationForm()
        return render(request, 'accounts/register_professor.html', {'form': form})

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied('El registro de usuarios internos solo se realiza por administracion.')
        form = ProfessorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Profesor {user.name} registrado exitosamente.')
            return redirect('accounts:login')
        return render(request, 'accounts/register_professor.html', {'form': form})

@login_required
def student_load_view(request):
    """
    Vista para profesor: panel de carga académica con datos cargados por AJAX.
    Restringe el acceso mediante validate_professor.
    """
    validate_professor(request.user)

    rooms = LegalRoom.objects.all()

    return render(request, 'accounts/student_load.html', {
        'page_title': 'Carga Académica',
        'rooms': rooms,
        'role_name': 'Profesor',
    })

@login_required
def auto_assign_cases_view(request):
    """
    Endpoint para activar la asignación automática. 
    Retorna JSON con los casos asignados.
    """
    validate_professor(request.user)
    if request.method == 'POST':
        assigned = auto_assign_cases(request.user)
        results = [
            {
                'id': c.id,
                'case': getattr(c, 'number', f"Caso {c.id}"),
                'student': c.student.user.name if c.student else "N/A",
                'status': c.status,
                'assigned_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
            } for c in assigned
        ]
        return JsonResponse({'assigned_cases': results}, status=200)
    return JsonResponse({'error': 'Method not allowed. Use POST.'}, status=405)


@login_required
def auto_assign_results_view(request):
    """
    Vista para consultar resultados de asignación.
    Muestra caso + estudiante asignado y permite ordenar por fecha o ID.
    """
    validate_professor(request.user)
    order = request.GET.get('order', 'id')
    order_by = 'id' if order == 'id' else '-created_at'
    assigned_cases = (
        AcademicCase.objects
        .select_related('student__user')
        .filter(status='Asignado', student__isnull=False)
        .order_by(order_by)
    )
    return render(request, 'accounts/auto_assign_results.html', {
        'page_title': 'Resultados de asignación',
        'role_name': get_user_role(request.user),
        'assigned_cases': assigned_cases,
        'selected_order': order,
    })


@login_required
def academic_metrics_view(request):
    """
    Vista para que el profesor consulte métricas académicas con filtros.
    """
    validate_professor(request.user)

    period = request.GET.get('period')
    room_id = request.GET.get('room')
    student_id = request.GET.get('student')

    global_metrics = get_global_metrics(period, room_id)
    
    students = Student.objects.select_related('user').all()
    if student_id:
        students = students.filter(id=student_id)

    students_metrics = []
    for student in students:
        metrics = get_student_metrics(student, period, room_id)
        metrics['name'] = student.user.name
        students_metrics.append(metrics)

    return render(request, 'accounts/academic_metrics.html', {
        'page_title': 'Métricas Académicas',
        'global_metrics': global_metrics,
        'students_metrics': students_metrics,
        'rooms': LegalRoom.objects.all(),
        'all_students': Student.objects.select_related('user').all(),
        'selected_period': period or '',
        'selected_room': room_id or '',
        'selected_student': student_id or '',
        'role_name': get_user_role(request.user),
    })


@login_required
def academic_dashboard_view(request):
    """JSON endpoint for professor academic dashboard data."""
    validate_professor(request.user)

    professor = getattr(request.user, 'professor_profile', None)
    if professor is None:
        return JsonResponse({'error': 'No professor profile found.'}, status=403)

    room = request.GET.get('room')
    data = get_academic_dashboard(professor, room=room)

    if not data['students']:
        return JsonResponse({
            'message': 'No students found for this professor.',
            'students': [],
            'summary': data['summary'],
        }, status=200)

    return JsonResponse(data, status=200)


@login_required
def professor_dashboard_view(request):
    if normalize_role_name(get_user_role(request.user)) != 'profesor':
        raise PermissionDenied
    return redirect('accounts:student-load')


@login_required
def student_dashboard_view(request):
    if normalize_role_name(get_user_role(request.user)) != 'estudiante':
        raise PermissionDenied

    if not hasattr(request.user, 'student_profile'):
        messages.error(request, 'No se encontró un perfil de estudiante asociado a este usuario.')
        return redirect('accounts:dashboard')

    student_profile = request.user.student_profile
    excluded_statuses = ['Cerrado', 'Cancelado', 'Finalizado', 'closed', 'cancelled', 'finalizado']
    active_assigned_cases = (
        request.user.assigned_cases
        .exclude(status__in=excluded_statuses)
        .select_related('professor__user', 'room')
        .order_by('-created_at')
    )

    history_records = []
    for case in active_assigned_cases:
        assignment_log = (
            case.logs
            .filter(event_type='asignacion')
            .order_by('created_at')
            .first()
        )
        assignment_date = assignment_log.created_at if assignment_log else case.created_at

        history_records.append({
            'number': case.number or f'CASO-{case.pk}',
            'status': case.status,
            'room': case.room.name if case.room else 'N/A',
            'professor': case.professor.user.name if case.professor else 'N/A',
            'assignment_date': assignment_date,
        })

    return render(request, 'accounts/student_dashboard.html', {
        'page_title': 'Dashboard del Estudiante',
        'role_name': get_user_role(request.user),
        'total_assigned_cases': student_profile.get_active_cases_count(),
        'assigned_cases': history_records,
    })


@login_required
def secretary_dashboard_view(request):
    role_name = normalize_role_name(get_user_role(request.user))
    if role_name.lower() not in ['secretaria', 'secretary'] and getattr(request.user, 'secretary_profile', None) is None:
        raise PermissionDenied
    return redirect('accounts:case-list')


@login_required
def beneficiary_dashboard_view(request):
    if normalize_role_name(get_user_role(request.user)) != 'beneficiario':
        raise PermissionDenied
    return redirect('accounts:beneficiary-cases')


@login_required
def system_statistics_view(request):
    """
    Vista para que la secretaria/coordinador consulte estadísticas académicas generales del sistema.
    """
    validate_coordinator(request.user)

    period = request.GET.get('period')
    room = request.GET.get('room')

    statistics = get_system_statistics(period, room)

    # Si es una petición AJAX, retornar JSON
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(statistics)

    # De lo contrario, renderizar template
    return render(request, 'accounts/system_statistics.html', {
        'page_title': 'Estadísticas Académicas del Sistema',
        'statistics': statistics,
        'rooms': LegalRoom.objects.all(),
        'selected_period': period or '',
        'selected_room': room or '',
        'role_name': get_user_role(request.user),
    })
    
# ============================================================
# PTCJMGA-55: Derecho al Olvido (Eliminación de Datos)
# ============================================================



class RequestDataDeletionView(LoginRequiredMixin, FormView):
    """
    Vista para que un beneficiario solicite la eliminación de sus datos.
    PTCJMGA-55 — Ley 1581 de 2012.

    Cubre los 3 escenarios Gherkin de la HU:
      1. Solicitud registrada → estado 'Pendiente'
      2. (admin la procesa después en otra vista)
      3. Bloqueo si tiene casos activos
    """

    template_name = 'accounts/request_data_deletion.html'
    form_class    = DataDeletionRequestForm
    success_url   = reverse_lazy('accounts:data-deletion-success')

    # Estados de Case que bloquean la eliminacion
    CASOS_ACTIVOS = ['Pendiente', 'Asignado', 'En proceso', 'En tramite']

    def dispatch(self, request, *args, **kwargs):
        """Solo beneficiarios pueden acceder a esta vista."""
        if not isinstance(request.user, Beneficiary):
            messages.error(request, 'Solo los beneficiarios pueden solicitar eliminacion de datos.')
            return redirect('accounts:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Agrega informacion sobre casos activos del beneficiario."""
        context = super().get_context_data(**kwargs)
        beneficiary = self.request.user

        casos_activos = RegistryCase.objects.filter(
            beneficiary=beneficiary,
            status__in=self.CASOS_ACTIVOS,
        )
        context['tiene_casos_activos'] = casos_activos.exists()
        context['casos_activos_count'] = casos_activos.count()

        context['solicitud_pendiente'] = DataDeletionRequest.objects.filter(
            beneficiary=beneficiary,
            status=DataDeletionRequest.STATUS_PENDIENTE,
        ).first()

        return context

    def form_valid(self, form):
        """
        Procesa la solicitud:
        - Bloquea si tiene casos activos (Escenario 3)
        - Bloquea si ya tiene una solicitud pendiente
        - Crea la solicitud en estado 'Pendiente' (Escenario 1)
        """
        beneficiary = self.request.user

        # Validacion 1: casos activos
        if RegistryCase.objects.filter(
            beneficiary=beneficiary,
            status__in=self.CASOS_ACTIVOS,
        ).exists():
            messages.error(
                self.request,
                'No es posible eliminar sus datos mientras tenga casos activos.',
            )
            return self.form_invalid(form)

        # Validacion 2: solicitud pendiente previa
        if DataDeletionRequest.objects.filter(
            beneficiary=beneficiary,
            status=DataDeletionRequest.STATUS_PENDIENTE,
        ).exists():
            messages.warning(
                self.request,
                'Ya tiene una solicitud de eliminacion pendiente de revision.',
            )
            return self.form_invalid(form)

        # Crear la solicitud
        solicitud = form.save(commit=False)
        solicitud.beneficiary = beneficiary
        solicitud.status      = DataDeletionRequest.STATUS_PENDIENTE
        solicitud.save()

        messages.success(
            self.request,
            'Su solicitud fue registrada exitosamente. El equipo administrativo '
            'la revisara y le notificara el resultado.',
        )
        return super().form_valid(form)


class DataDeletionSuccessView(LoginRequiredMixin, TemplateView):
    """Pagina de confirmacion tras enviar la solicitud."""
    template_name = 'accounts/data_deletion_success.html'


def custom_404_view(request, exception=None):  # noqa: ARG001
    return render(request, '404.html', status=404)
    
 # ============================================================
# PTCJMGA-50: Reportes Legales para Entidades Gubernamentales
# ============================================================

from datetime import datetime
from django.http import HttpResponse
from .services.legal_report import LegalReportGenerator


class LegalReportView(LoginRequiredMixin, View):
    """
    Vista para que la secretaria genere reportes legales en PDF.
    PTCJMGA-50 — Ley 2113 de 2021.

    GET: muestra el formulario de filtros + resumen previo.
    POST: genera el PDF y lo descarga.
    """

    template_name = 'accounts/legal_report.html'

    def dispatch(self, request, *args, **kwargs):
        """Solo secretaria o admin pueden acceder."""
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        user_role = getattr(request.user, 'role', None)
        if not user_role:
            messages.error(request, 'Su usuario no tiene un rol asignado.')
            return redirect('accounts:dashboard')

        role_name = user_role.name.lower()
        if role_name not in ['secretary', 'secretaria', 'admin']:
            messages.error(
                request,
                'No tiene permisos para acceder a los reportes legales. '
                'Esta funcion es exclusiva de la secretaria.'
            )
            return redirect('accounts:dashboard')

        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        """Muestra el formulario con resumen previo (sin filtros aplicados aun)."""
        generator = LegalReportGenerator()
        cases = generator.get_closed_cases()
        incomplete = generator.detect_incomplete_cases(cases)

        return render(request, self.template_name, {
            'total_cases_cerrados': cases.count(),
            'incomplete_cases': len(incomplete),
        })

    def post(self, request):
        """Genera el PDF segun los filtros enviados y lo descarga."""
        # Parsear fechas del form
        date_from_str = request.POST.get('date_from')
        date_to_str   = request.POST.get('date_to')

        date_from = self._parse_date(date_from_str)
        date_to   = self._parse_date(date_to_str)

        # Generar reporte
        generator = LegalReportGenerator(date_from=date_from, date_to=date_to)
        cases = generator.get_closed_cases()
        pdf_buffer = generator.generate_pdf(
            cases,
            secretary_name=request.user.name,
        )

        # Preparar la respuesta como descarga
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f'reporte_legal_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    @staticmethod
    def _parse_date(date_str):
        """Convierte un string 'YYYY-MM-DD' a objeto date. Retorna None si vacio o invalido."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None
