import json
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_GET
from django.db import transaction
from django.db.models import Avg
from django.urls import reverse
from django.utils import timezone


from django.utils.dateparse import parse_datetime
from django.contrib import messages

from cases.models import Appointment, AppointmentLog

from accounts.utils import get_user_role,  normalize_role_name, validate_coordinator, validate_professor_legal_room_access
from cases.models import AcademicAction, AcademicRecordTraceability, Case, CaseLog, AssignmentCriteriaConfig, AssignmentCriteriaLog
from .forms import AssignmentCriteriaForm
# cases/views.py — agregar al final

from django.views.decorators.http import require_http_methods
from cases.models import CommunicationLog
from notifications.services import send_notification

@login_required
@require_GET
def academic_action_traceability_view(request, id):
    action = get_object_or_404(
        AcademicAction.objects.select_related(
            'case',
            'case__room',
            'case__student__user',
            'registered_by__user',
        ),
        pk=id,
    )
    validate_professor_legal_room_access(request.user, action.case)

    traces = list(
        AcademicRecordTraceability.objects.filter(academic_action=action)
        .select_related('modified_by')
        .order_by('-created_at', '-id')
    )

    if traces:
        history_records = traces
    else:
        history_records = [{
            'created_at': action.registered_at,
            'modified_by': action.registered_by.user,
            'field_name': 'academic_action',
            'old_value': '',
            'new_value': str(action.grade),
            'event_type': AcademicRecordTraceability.EVENT_CREATE,
        }]

    return render(request, 'cases/academic_action_traceability.html', {
        'action': action,
        'history_records': history_records,
        'page_title': 'Trazabilidad academica',
    })

class RegisterAcademicActionView(LoginRequiredMixin, View):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 1: endpoint POST que registra una acción académica calificable
    sobre un caso activo. Requiere autenticación.
    Retorna 401 si no autenticado, 400 si datos inválidos, 201 si exitoso.
    
    Validaciones:
    - Solo profesores pueden registrar acciones
    - Profesor solo registra en sus propios casos
    - Caso debe estar activo
    - Nota debe estar en rango 0.0-5.0
    """

    def handle_no_permission(self):
        # Sobreescribimos el comportamiento por defecto de LoginRequiredMixin
        # que redirige al login — para una API JSON retornamos 401 directamente
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def post(self, request):
        """
        Criterio 1: registra una acción académica calificable sobre un caso activo.
        Campos requeridos: case_id, action_type, grade
        Campos opcionales: observation, attended, arrival_time, document_delivered
        
        Validaciones adicionales:
        - Solo profesor asesor puede registrar
        - Nota debe estar 0.0-5.0
        """
        # Validar que el usuario sea profesor
        if not hasattr(request.user, 'professor_profile'):
            return JsonResponse({'error': 'Solo profesores pueden registrar acciones académicas'}, status=403)

        professor = request.user.professor_profile

        try:
            # Parsear el body JSON de la petición
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        case_id     = body.get('case_id')
        action_type = body.get('action_type')
        grade       = body.get('grade')

        # Validar que los campos obligatorios estén presentes
        if not all([case_id, action_type, grade is not None]):
            return JsonResponse({'error': 'case_id, action_type y grade son obligatorios'}, status=400)

        # Buscar el caso — retorna 404 si no existe
        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            return JsonResponse({'error': 'Caso no encontrado'}, status=404)

        # Validar que el profesor sea el asesor del caso
        # Backend: Restricción de permisos - Solo profesor asesor de la sala
        if case.professor != professor:
            return JsonResponse({'error': 'Solo el profesor asesor puede registrar acciones en este caso'}, status=403)

        # Criterio 1: solo se pueden registrar acciones en casos no cerrados
        if case.status == 'Cerrado':
            return JsonResponse({'error': 'No se pueden registrar acciones en casos cerrados'}, status=400)

        # Validar rango de nota
        try:
            grade_float = float(grade)
            if grade_float < 0.0 or grade_float > 5.0:
                return JsonResponse({'error': 'La nota debe estar entre 0.0 y 5.0'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'La nota debe ser un número válido'}, status=400)

        # Construir la acción con los campos opcionales de asistencia
        action = AcademicAction(
            case=case,
            action_type=action_type,
            grade=grade,
            observation=body.get('observation', ''),
            registered_by=professor,
            attended=body.get('attended', None),
            arrival_time=body.get('arrival_time', None),
            document_delivered=body.get('document_delivered', None),
        )

        # Ejecutar validaciones del modelo (rango de nota, inmutabilidad)
        try:
            action.full_clean()
        except ValidationError as e:
            return JsonResponse({'error': str(e)}, status=400)

        # Persistir la acción en la BD
        action.save()

        return JsonResponse({
            'id': action.id,
            'action_type': action.action_type,
            'grade': float(action.grade),
            'registered_at': action.registered_at.isoformat(),
        }, status=201)


@login_required
def case_detail_view(request, case_id):
    case = get_object_or_404(Case, id=case_id)
    appointments = Appointment.objects.filter(
        case=case
    ).order_by('-scheduled_datetime')

    return render(request, 'cases/case_detail.html', {
        'case':         case,
        'appointments': appointments,
    })


@login_required
def assignment_criteria_view(request):
    try:
        validate_coordinator(request.user)
    except PermissionDenied:
        messages.error(request, 'Acceso denegado. Solo secretarios o administradores pueden acceder a esta sección.')
        return redirect('accounts:dashboard')

    config = AssignmentCriteriaConfig.objects.filter(active=True).order_by('-updated_at').first()
    if config is None:
        config = AssignmentCriteriaConfig.objects.order_by('-updated_at').first()
    if config is None:
        config = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=1)

    form = AssignmentCriteriaForm(instance=config)
    return render(request, 'cases/assignment_criteria.html', {
        'form': form,
        'page_title': 'Criterios de asignación',
    })


@login_required
def update_assignment_criteria_view(request):
    try:
        validate_coordinator(request.user)
    except PermissionDenied:
        messages.error(request, 'Acceso denegado. Solo secretarios o administradores pueden acceder a esta sección.')
        return redirect('accounts:dashboard')

    config = AssignmentCriteriaConfig.objects.filter(active=True).order_by('-updated_at').first()
    if config is None:
        config = AssignmentCriteriaConfig.objects.order_by('-updated_at').first()
    if config is None:
        config = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=1)

    form = AssignmentCriteriaForm(request.POST or None, instance=config)
    if request.method == 'POST' and form.is_valid():
        # Detectar cambios reales y registrar un log por campo modificado
        changed_fields = []
        watched_fields = ['max_cases_per_professor', 'prioritize_same_room', 'balance_workload', 'active']
        for f in watched_fields:
            old = getattr(config, f)
            new = form.cleaned_data.get(f)
            if old != new:
                changed_fields.append((f, old, new))

        with transaction.atomic():
            updated_config = form.save(commit=False)
            if updated_config.active:
                AssignmentCriteriaConfig.objects.exclude(pk=updated_config.pk).filter(active=True).update(active=False)
            updated_config.save()

            # Registrar logs in bloque atómico para mantener consistencia; historial inmutable
            if changed_fields:
                logs = []
                for field_name, old_val, new_val in changed_fields:
                    logs.append(AssignmentCriteriaLog(
                        criteria=updated_config,
                        changed_by=request.user,
                        field_name=field_name,
                        old_value=str(old_val) if old_val is not None else None,
                        new_value=str(new_val) if new_val is not None else None,
                    ))
                AssignmentCriteriaLog.objects.bulk_create(logs)

        messages.success(request, 'Configuración de criterios de asignación actualizada con éxito.')
        return redirect('cases:assignment-criteria')

    return render(request, 'cases/assignment_criteria.html', {
        'form': form,
        'page_title': 'Criterios de asignación',
    })
class AcademicActionFormView(LoginRequiredMixin, View):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Criterio 1: vista GET que renderiza el formulario de registro
    de acción académica para un caso específico.
    
    Validaciones:
    - Solo profesores pueden acceder
    - Profesor solo accede a sus propios casos
    - Caso debe estar activo
    """

    def get(self, request, case_id):
        """
        Renderiza el formulario de registro de acción académica.
        Pasa el caso y las acciones previas al template.
        """
        # Validar que el usuario sea profesor
        if not hasattr(request.user, 'professor_profile'):
            messages.error(request, 'Acceso denegado. Solo profesores pueden registrar acciones académicas.')
            return redirect('accounts:dashboard')

        professor = request.user.professor_profile

        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            messages.error(request, 'Caso no encontrado.')
            return redirect('accounts:dashboard')

        # Validar que el profesor sea el asesor del caso
        if case.professor != professor:
            messages.error(request, 'Acceso denegado. Solo el profesor asesor puede registrar acciones en este caso.')
            return redirect('accounts:dashboard')

        # Validar que el caso no esté cerrado
        if case.status == 'Cerrado':
            messages.error(request, 'No se pueden registrar acciones en casos cerrados.')
            return redirect('accounts:dashboard')

        # Obtener acciones previas para mostrar historial
        actions = (
            AcademicAction.objects.filter(case=case)
            .select_related('registered_by__user')
            .order_by('-registered_at')
        )

        academic_action_config = {
            'caseId': case.id,
            'partialGradeUrl': reverse('cases:get-partial-grade', args=[case.id]),
            'registerActionUrl': reverse('cases:register-academic-action'),
        }
        # PTCJMGA-XX: Sancion academica - datos para el boton y modal
        from accounts.models import Student
        available_students = Student.objects.select_related('user').exclude(
            id=case.student.id if case.student else 0
        ).order_by('user__name')

        # Verificar si el usuario puede aplicar sanciones
        user_role = getattr(request.user, 'role', None)
        is_professor = (
            request.user.is_superuser or
            request.user.is_staff or
            (user_role and user_role.name.lower() in ['professor', 'profesor', 'admin', 'coordinator', 'coordinador'])
        )

        # Leer y limpiar el modal de feedback (si viene de aplicar sancion)
        sancion_modal = request.session.pop('sancion_modal', None)

        return render(request, 'cases/register_academic_action.html', {
            'case': case,
            'actions': actions,
            'page_title': 'Acción académica',
            'role_name': get_user_role(request.user),
            'academic_action_config': academic_action_config,
            'available_students': available_students,   
            'is_professor': is_professor,                
            'sancion_modal': sancion_modal,             
            'user_name': request.user.name,       
        })
class GetPartialGradeView(LoginRequiredMixin, View):
    def get(self, request, case_id):
        try:
            result = AcademicAction.objects.filter(case_id=case_id).aggregate(Avg('grade'))
            avg_grade = result['grade__avg']
            if avg_grade is None:
                return JsonResponse({'partial_grade': 0.0})
            return JsonResponse({'partial_grade': round(avg_grade, 1)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@login_required
def case_list_view(request):
    """
    Case listing view with filtering by status.
    Only for authenticated users with role 'secretaria'.
    Accepts query param 'status' (activos/cerrados), defaults to 'activos'.
    Returns JSON list of cases with number, beneficiary name, status.
    """
    if normalize_role_name(get_user_role(request.user)) != 'secretaria':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    # Default to 'activos' if status is missing or invalid
    status = request.GET.get('status', 'activos').lower()
    allowed_statuses = ['activos', 'cerrados']
    
    if status not in allowed_statuses:
        status = 'activos'
    
    from cases.services import filter_cases_by_status
    queryset = filter_cases_by_status(status)
    # Select related to avoid N+1 queries
    cases = queryset.select_related('beneficiary').values('id', 'number', 'beneficiary__name', 'status')
    cases = list(cases)

    response_data = [
        {
            "id":          case['id'],
            "number":      case['number'],
            "beneficiary": case['beneficiary__name'],
            "status":      case['status']
        }
        for case in cases
    ]
    
    return JsonResponse(response_data, safe=False)

class CaseStatusUpdateView(LoginRequiredMixin, View):

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def post(self, request, pk):
        try:
            case = Case.objects.select_related('beneficiary', 'room').get(pk=pk)
        except Case.DoesNotExist:
            return JsonResponse({'error': 'Caso no encontrado'}, status=404)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        new_status = body.get('status')
        if not new_status:
            return JsonResponse({'error': 'El campo status es obligatorio'}, status=400)

        old_status = case.status
        case.status = new_status
        case.save()

        # Estados que no disparan notificación
        if new_status == 'Pendiente':
            return JsonResponse({'status': 'actualizado', 'new_status': new_status})

        # Determinar event_type para bitácora
        event_type = 'asignacion' if new_status == 'Asignado' else 'reasignacion'

        # Verificar si el beneficiario tiene correo
        beneficiary = case.beneficiary
        if not beneficiary or not beneficiary.email:
            CaseLog.objects.create(
                case=case,
                event_type='error_notificacion',
                description='No se envió notificación: el beneficiario no tiene correo registrado.',
                executed_by=request.user,
            )
            return JsonResponse({'status': 'actualizado', 'new_status': new_status})

        # Registrar en bitácora
        CaseLog.objects.create(
            case=case,
            event_type=event_type,
            description=f'Estado cambiado de {old_status} a {new_status}.',
            executed_by=request.user,
        )

        # Enviar notificación al beneficiario
        from notifications.services import send_notification
        try:
            send_notification(
                to=beneficiary.email,
                subject=f'Actualización de tu caso — {case.pk}',
                body=(
                    f'Hola {beneficiary.name},\n\n'
                    f'El estado de tu caso #{case.pk} ha sido actualizado.\n'
                    f'Estado anterior: {old_status}\n'
                    f'Nuevo estado: {new_status}\n'
                    f'Fecha: {timezone.now().strftime("%d/%m/%Y %H:%M")}\n\n'
                    f'Para más información comunícate con el consultorio jurídico.\n'
                )
            )
        except Exception as e:
            CaseLog.objects.create(
                case=case,
                event_type='error_notificacion',
                description=f'Error al enviar notificación al beneficiario: {e}',
                executed_by=request.user,
            )

        return JsonResponse({'status': 'actualizado', 'new_status': new_status})


@login_required
def student_cases_view(request):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Indicador de semáforo visible en la lista de casos del estudiante

    Given el estudiante ha iniciado sesión
    And tiene casos activos con fecha límite legal registrada
    When el sistema carga la lista de casos del estudiante
    Then los casos con ≤ 1 días restantes muestran indicador ROJO (Urgente)
    And los casos con 2 días restantes muestran indicador AMARILLO (Atención)
    And los casos con > 3 días restantes muestran indicador VERDE (Normal)
    And los indicadores se actualizan automáticamente cada 24 horas

    Endpoint GET que retorna los casos activos del estudiante con semáforo.
    Solo accesible para usuarios con rol 'STUDENT'.
    """
    # Verificar que el usuario esté autenticado (ya manejado por @login_required)
    # Verificar rol del usuario
    if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name != 'STUDENT':
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Obtener el perfil de estudiante
    try:
        student = request.user.student_profile
    except student.DoesNotExist:
        return JsonResponse({'error': 'Student profile not found'}, status=404)

    # Obtener casos activos del estudiante
    cases = Case.objects.filter(
        student=student,
        status='active'
    ).select_related('beneficiary').order_by('legal_deadline')

    today = timezone.now().date()
    response_data = []

    for case in cases:
        days_remaining = (case.legal_deadline - today).days

        # Determinar semáforo
        if days_remaining <= 1:
            semaphore = 'red'
        elif days_remaining == 2:
            semaphore = 'yellow'
        else:
            semaphore = 'green'

        response_data.append({
            'id': case.id,
            'number': case.number,
            'beneficiary_name': case.beneficiary.name if case.beneficiary else '',
            'days_remaining': days_remaining,
            'semaphore': semaphore,
        })

    return JsonResponse(response_data, safe=False)


class StudentCasesView(LoginRequiredMixin, View):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Indicador de semáforo visible en la lista de casos del estudiante

    Class-based view para endpoint GET de casos del estudiante con semáforo.
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        # Verificar rol del usuario
        if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name != 'STUDENT':
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Obtener el perfil de estudiante
        try:
            student = request.user.student_profile
        except student.DoesNotExist:
            return JsonResponse({'error': 'Student profile not found'}, status=404)

        # Obtener casos activos del estudiante
        cases = Case.objects.filter(
            student=student,
            status='active'
        ).select_related('beneficiary').order_by('legal_deadline')

        today = timezone.now().date()
        response_data = []

        for case in cases:
            days_remaining = (case.legal_deadline - today).days

            # Determinar semáforo
            if days_remaining <= 1:
                semaphore = 'red'
            elif days_remaining == 2:
                semaphore = 'yellow'
            else:
                semaphore = 'green'

            response_data.append({
                'id': case.id,
                'number': case.number,
                'beneficiary_name': case.beneficiary.name if case.beneficiary else '',
                'days_remaining': days_remaining,
                'semaphore': semaphore,
            })

        return JsonResponse(response_data, safe=False)


class StudentDeadlineSummaryView(LoginRequiredMixin, View):
    """
    HU: Alertas visuales y por correo cuando un caso se acerca a su fecha límite legal
    Criterio: Pantalla de vencimientos al iniciar sesión

    Pantalla de resumen de vencimientos que se muestra antes del dashboard principal
    cuando el estudiante tiene casos con término legal a ≤ 7 días.
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        # Verificar rol del usuario
        if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name != 'STUDENT':
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Obtener el perfil de estudiante
        try:
            student = request.user.student_profile
        except student.DoesNotExist:
            return JsonResponse({'error': 'Student profile not found'}, status=404)

        # Obtener casos activos del estudiante con ≤ 7 días restantes
        today = timezone.now().date()
        critical_cases = []

        cases = Case.objects.filter(
            student=student,
            status='active'
        ).select_related('beneficiary')

        for case in cases:
            days_remaining = (case.legal_deadline - today).days
            if days_remaining <= 7:
                # Determinar semáforo
                if days_remaining <= 1:
                    semaphore = 'red'
                elif days_remaining == 2:
                    semaphore = 'yellow'
                else:
                    semaphore = 'green'

                critical_cases.append({
                    'id': case.id,
                    'number': case.number,
                    'beneficiary_name': case.beneficiary.name if case.beneficiary else '',
                    'days_remaining': days_remaining,
                    'semaphore': semaphore,
                })

        # Ordenar por días restantes (menor a mayor)
        critical_cases.sort(key=lambda x: x['days_remaining'])

        # Si no hay casos críticos, redirigir al dashboard
        if not critical_cases:
            from django.urls import reverse
            return redirect(reverse('accounts:student-history'))

        # Renderizar template con los casos críticos
        return render(request, 'cases/student_deadline_summary.html', {
            'critical_cases': critical_cases,
            'page_title': 'Resumen de Vencimientos',
        })


class ProfessorCasesView(LoginRequiredMixin, View):

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        # Verificar rol — comparación case-insensitive
        if not hasattr(request.user, 'role') or request.user.role is None:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        if request.user.role.name.lower() not in ['professor', 'profesor']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        try:
            professor = request.user.professor_profile
        except:
            return JsonResponse({'error': 'Professor profile not found'}, status=404)

        if not hasattr(request.user, 'room') or request.user.room is None:
            return JsonResponse({'error': 'Professor has no assigned room'}, status=400)

        room = request.user.room

        cases = Case.objects.filter(
            professor=professor,
            room=room,
            status='active'
        ).select_related('student__user', 'beneficiary').order_by('legal_deadline')

        today = timezone.now().date()
        response_data = []

        for case in cases:
            days_remaining = (case.legal_deadline - today).days

            if days_remaining <= 1:
                semaphore = 'red'
            elif days_remaining == 2:
                semaphore = 'yellow'
            else:
                semaphore = 'green'

            response_data.append({
                'id':             case.id,
                'number':         case.number or f'Caso {case.id}',
                'student_name':   case.student.user.name if case.student else 'Sin asignar',
                'beneficiary':    case.beneficiary.name if case.beneficiary else 'Sin asignar',
                'status':         case.status,
                'days_remaining': days_remaining,
                'semaphore':      semaphore,
            })

        response_data.sort(key=lambda x: (x['semaphore'] != 'red', x['days_remaining']))

        return JsonResponse(response_data, safe=False)


class ProfessorDeadlineSummaryView(LoginRequiredMixin, View):
    """
    HU: Como profesor asesor, quiero recibir alertas y ver en mi panel los casos
    de mi sala que se acercan a su fecha límite legal
    
    Criterio: Pantalla de vencimientos al iniciar sesión (profesor)
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        # Verificar rol del usuario
        if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name.lower() not in ['professor', 'profesor']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Obtener el perfil de profesor
        try:
            professor = request.user.professor_profile
        except:
            return JsonResponse({'error': 'Professor profile not found'}, status=404)

        # Obtener la sala del profesor
        if not hasattr(request.user, 'room') or request.user.room is None:
            return JsonResponse({'error': 'Professor has no assigned room'}, status=400)

        room = request.user.room

        # Obtener casos activos de la sala con ≤ 7 días restantes
        today = timezone.now().date()
        critical_cases = []

        cases = Case.objects.filter(
            professor=professor,
            room=room,
            status='active'
        ).select_related('student__user', 'beneficiary')

        for case in cases:
            days_remaining = (case.legal_deadline - today).days
            if days_remaining <= 7:
                # Determinar semáforo
                if days_remaining <= 1:
                    semaphore = 'red'
                elif days_remaining == 2:
                    semaphore = 'yellow'
                else:
                    semaphore = 'green'

                critical_cases.append({
                    'id': case.id,
                    'number': case.number,
                    'student_name': case.student.user.name if case.student else '',
                    'days_remaining': days_remaining,
                    'semaphore': semaphore,
                })

        # Ordenar por días restantes (menor a mayor)
        critical_cases.sort(key=lambda x: x['days_remaining'])

        # Si no hay casos críticos, redirigir al dashboard
        if not critical_cases:
            from django.urls import reverse
            return redirect(reverse('accounts:professor-dashboard'))

        # Renderizar template con los casos críticos
        return render(request, 'cases/professor_deadline_summary.html', {
            'critical_cases': critical_cases,
            'page_title': 'Resumen de Vencimientos - Profesor',
        })


class ProfessorStudentsForGradingView(LoginRequiredMixin, View):
    """
    HU: Registro de acciones académicas calificables desde el caso
    Conexión Frontend: Lista los casos del profesor para que acceda al formulario de calificación.
    
    GET: Renderiza lista de estudiantes/casos del profesor en su sala para acceder al formulario de calificación.
    """

    def get(self, request):
        # Verificar que el usuario es profesor
        if not hasattr(request.user, 'professor_profile'):
            messages.error(request, 'Acceso denegado. Solo profesores pueden acceder a esta sección.')
            return redirect('accounts:dashboard')

        professor = request.user.professor_profile
        
        # Obtener todos los casos no cerrados del profesor
        cases = Case.objects.filter(
            professor=professor,
        ).exclude(
            status='Cerrado'
        ).select_related(
            'student__user',
            'room'
        ).prefetch_related(
            'academic_actions'
        ).order_by('room__name', 'student__user__name')

        # Agrupar por sala para mejor visualización
        cases_by_room = {}
        for case in cases:
            room_name = case.room.name if case.room else 'Sin sala'
            if room_name not in cases_by_room:
                cases_by_room[room_name] = []
            
            # Calcular promedio de notas parcial
            partial_grade = case.academic_actions.aggregate(Avg('grade'))['grade__avg'] or 0.0
            
            cases_by_room[room_name].append({
                'case': case,
                'student_name': case.student.user.name if case.student else 'Sin estudiante',
                'partial_grade': round(float(partial_grade), 1),
                'action_count': case.academic_actions.count(),
                'form_url': reverse('cases:academic-action-form', args=[case.id]),
            })

        return render(request, 'cases/professor_students_for_grading.html', {
            'page_title': 'Calificar Estudiante',
            'cases_by_room': cases_by_room,
            'professor_name': professor.user.name,
            'role_name': get_user_role(request.user),
        })

    
@login_required
def reschedule_appointment(request, appointment_id):
    """
    Permite a la secretaria reprogramar una cita.
    Adjunta el motivo y el actor al instance para que el signal los capture.
    """
    appointment = get_object_or_404(Appointment, pk=appointment_id)

    # Solo la secretaria puede reprogramar
    user_role = getattr(request.user, 'role', None)
    role_name = user_role.name.lower() if user_role else ''
    if role_name not in ['secretaria', 'secretary']:
        messages.error(request, 'No tiene permisos para reprogramar citas.')
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        new_datetime_str = request.POST.get('new_datetime', '').strip()
        reason           = request.POST.get('reason', '').strip()

        new_dt = parse_datetime(new_datetime_str)
        if not new_dt:
            messages.error(request, 'La fecha ingresada no es válida.')
            return render(request, 'cases/reschedule_appointment.html', {
                'appointment': appointment,
            })

        if timezone.is_naive(new_dt):
            new_dt = timezone.make_aware(new_dt)

        # Adjuntar datos al instance para que el signal los capture
        appointment._reschedule_reason = reason
        appointment._changed_by        = request.user
        appointment.scheduled_datetime = new_dt
        appointment.save()

        messages.success(request, 'Cita reprogramada exitosamente.')
        return redirect('cases:appointment_history', appointment_id=appointment.id)

    return render(request, 'cases/reschedule_appointment.html', {
        'appointment': appointment,
    })


@login_required
def appointment_history(request, appointment_id):
    """
    Muestra el historial cronológico de reprogramaciones de una cita.
    Vista de solo lectura — accesible para el profesor de la sala.
    """
    appointment = get_object_or_404(Appointment, pk=appointment_id)

    logs = AppointmentLog.objects.filter(
        appointment=appointment
    ).order_by('changed_at')

    return render(request, 'cases/appointment_history.html', {
        'appointment': appointment,
        'logs':        logs,
        'case':        appointment.case,
    })


def _is_professor(user):
    """Verifica si el usuario tiene rol de profesor."""
    role = getattr(user, 'role', None)
    return role and role.name.lower() in ['profesor', 'professor']


@login_required
def email_recipients(request, case_id):
    """
    Retorna la lista de destinatarios disponibles para un caso.
    Solo accesible para el profesor del caso.
    """
    from cases.models import Case

    case = get_object_or_404(Case, pk=case_id)

    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    recipients = []

    # Agregar estudiante si tiene correo
    if case.student and case.student.user.email:
        recipients.append({
            'name':  case.student.user.name,
            'email': case.student.user.email,
            'role':  'Estudiante',
        })

    # Agregar beneficiario si tiene correo
    if case.beneficiary and case.beneficiary.email and case.beneficiary.email.strip():
        recipients.append({
            'name':  case.beneficiary.name,
            'email': case.beneficiary.email,
            'role':  'Beneficiario',
        })

    return JsonResponse({'recipients': recipients})


@login_required
@require_http_methods(['POST'])
def send_case_email(request, case_id):
    """
    Permite al profesor enviar un correo institucional
    a los destinatarios del caso. Registra en CommunicationLog.
    """
    from cases.models import Case

    case = get_object_or_404(Case, pk=case_id)

    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido.'}, status=400)

    subject    = data.get('subject', '').strip()
    body       = data.get('body', '').strip()
    recipients = data.get('recipients', [])

    # Validaciones
    if not subject:
        return JsonResponse({'error': 'El asunto es obligatorio.'}, status=400)
    if not body:
        return JsonResponse({'error': 'El cuerpo del mensaje es obligatorio.'}, status=400)
    if not recipients:
        return JsonResponse({'error': 'Debe seleccionar al menos un destinatario.'}, status=400)

    # Construir cuerpo final con referencia del caso
    full_body = (
        f"{body}\n\n"
        f"---\n"
        f"Referencia: Caso {case.id} — {case.room.name}\n"
        f"Este mensaje fue enviado desde el sistema BURO.\n"
    )

    # Intentar envío a cada destinatario
    send_errors = []
    for email in recipients:
        try:
            send_notification(to=email, subject=subject, body=full_body)
        except Exception as e:
            from notifications.models import FailedNotification
            # Registrar fallo explícitamente en la view
            FailedNotification.objects.create(
                to=email,
                subject=subject,
                body=full_body,
                error_message=str(e),
            )
            send_errors.append({'email': email, 'error': str(e)})

    # Determinar status general
    status = 'fallido' if send_errors else 'enviado'

    # Registrar en bitácora sin importar el resultado
    CommunicationLog.objects.create(
        case=case,
        sent_by=request.user,
        recipients=recipients,
        subject=subject,
        body=full_body,
        status=status,
    )

    if send_errors:
        return JsonResponse({
            'error':  'No fue posible enviar el correo a algunos destinatarios.',
            'detail': send_errors,
        }, status=200)

    return JsonResponse({'message': 'Correo enviado exitosamente.'}, status=200)


@login_required
def communication_history(request, case_id):
    """
    Muestra el historial de correos institucionales del caso.
    Solo accesible para el profesor.
    """
    from cases.models import Case

    case = get_object_or_404(Case, pk=case_id)

    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    logs = CommunicationLog.objects.filter(
        case=case
    ).order_by('-sent_at')

    return render(request, 'cases/communication_history.html', {
        'case': case,
        'logs': logs,
    })

@login_required
def compose_case_email(request, case_id):
    """Renderiza el formulario de redacción de correo institucional."""
    from cases.models import Case

    case = get_object_or_404(Case, pk=case_id)

    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    return render(request, 'cases/compose_case_email.html', {'case': case})


@login_required
def professor_appointment_alerts(request):
    """
    Panel de alertas para profesores:
    - Reprogramaciones sin motivo (últimos 30 días)
    - Casos con vencimiento crítico (≤ 7 días)
    """
    from datetime import timedelta

    if not _is_professor(request.user):
        return redirect('accounts:dashboard')

    try:
        professor = request.user.professor_profile
    except Exception:
        return redirect('accounts:dashboard')

    # 1. Reprogramaciones sin motivo
    thirty_days_ago = timezone.now() - timedelta(days=30)
    reschedule_alerts = AppointmentLog.objects.filter(
        appointment__case__professor=professor,
        no_reason_flag=True,
        changed_at__gte=thirty_days_ago,
    ).select_related(
        'appointment__case__room',
        'appointment__case__student__user',
        'appointment__case__beneficiary',
        'changed_by__role',
    ).order_by('-changed_at')

    # 2. Casos con vencimiento crítico (≤ 7 días)
    today = timezone.now().date()
    critical_cases = []
    cases = Case.objects.filter(
        professor=professor,
        status__in=['active', 'Asignado', 'En proceso'],
        legal_deadline__lte=today + timedelta(days=7),
    ).select_related('student__user', 'beneficiary', 'room')

    for case in cases:
        days_remaining = (case.legal_deadline - today).days
        critical_cases.append({
            'case':           case,
            'days_remaining': days_remaining,
            'semaphore':      'red' if days_remaining <= 1 else 'yellow',
        })

    critical_cases.sort(key=lambda x: x['days_remaining'])

    return render(request, 'cases/professor_appointment_alerts.html', {
        'alerts':          reschedule_alerts,
        'critical_cases':  critical_cases,
        'page_title':      'Alertas',
    })


@login_required
def professor_appointment_alerts_count(request):
    """
    Endpoint que retorna el número de alertas pendientes del profesor.
    Útil para mostrar badge en navbar.
    """
    from datetime import timedelta
    
    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    try:
        professor = request.user.professor_profile
    except:
        return JsonResponse({'count': 0})

    thirty_days_ago = timezone.now() - timedelta(days=30)
    count = (
        AppointmentLog.objects
        .filter(
            appointment__case__professor=professor,
            no_reason_flag=True,
            changed_at__gte=thirty_days_ago,
        )
        .count()
    )

    return JsonResponse({'count': count})


@login_required
@require_http_methods(['POST'])
def retry_failed_notification(request, case_id, log_id):
    """
    Reintenta enviar una notificación que falló previamente.
    Busca en FailedNotification y reintenta el envío.
    """
    from cases.models import Case
    from notifications.models import FailedNotification

    case = get_object_or_404(Case, pk=case_id)

    if not _is_professor(request.user):
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    try:
        failed_notif = FailedNotification.objects.get(pk=log_id)
    except FailedNotification.DoesNotExist:
        return JsonResponse({'error': 'Notificación no encontrada.'}, status=404)

    # Intentar reenvío
    try:
        send_notification(
            to=failed_notif.to,
            subject=failed_notif.subject,
            body=failed_notif.body,
        )
        
        # Marcar como resuelta
        failed_notif.resolved = True
        failed_notif.resolved_at = timezone.now()
        failed_notif.save()

        return JsonResponse({
            'status': 'enviado',
            'message': 'Correo reenviado exitosamente.'
        })

    except Exception as e:
        # Actualizar error message pero mantener sin resolver
        failed_notif.error_message = str(e)
        failed_notif.save()

        return JsonResponse({
            'status': 'fallo',
            'error': f'No fue posible reenviar: {str(e)}',
        }, status=200)
    
@login_required
def professor_cases_page(request):
    """Renderiza la página de casos del profesor."""
    if not _is_professor(request.user):
        return redirect('accounts:dashboard')

    return render(request, 'cases/professor_cases.html', {
        'page_title': 'Mis casos',
    })# ============================================================
# PTCJMGA-XX: Sancion academica (reasignacion como sancion)
# ============================================================

from cases.services import SanctionService


class ApplySanctionView(LoginRequiredMixin, View):
    """
    PTCJMGA-XX: Vista para aplicar sancion academica sobre un caso.

    Solo accesible para profesores, coordinadores o admin.
    Recibe POST con: case_id (URL), student_id, reason.
    Reasigna el caso al estudiante sancionado y crea registro inmutable.
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticacion requerida'}, status=401)

    def post(self, request, case_id):
        """
        Aplica la sancion academica.

        Espera form-encoded o JSON con:
            student_id: ID del estudiante a sancionar
            reason: motivo de la sancion (obligatorio)
        """
        # Parsear datos del request (acepta form o JSON)
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'JSON invalido'}, status=400)
            student_id = body.get('student_id')
            reason = body.get('reason', '')
        else:
            student_id = request.POST.get('student_id')
            reason = request.POST.get('reason', '')

        # Validar campos obligatorios
        if not student_id:
            messages.error(request, 'Debe seleccionar el estudiante a sancionar.')
            return redirect('cases:case-detail', case_id=case_id)

        if not reason or not reason.strip():
            request.session['sancion_modal'] = {
            'tipo': 'warning',
            'mensaje': 'El motivo de la sanción es obligatorio.',
            }
            return redirect('cases:case-detail', case_id=case_id)

        # Buscar el caso
        try:
            case = Case.objects.select_related('student__user').get(pk=case_id)
        except Case.DoesNotExist:
            messages.error(request, 'Caso no encontrado.')
            return redirect('accounts:dashboard')

        # Buscar el estudiante a sancionar
        from accounts.models import Student
        try:
            sanctioned_student = Student.objects.select_related('user').get(pk=student_id)
        except Student.DoesNotExist:
            messages.error(request, 'Estudiante no encontrado.')
            return redirect('cases:case-detail', case_id=case_id)

        # Aplicar la sancion
        try:
            log = SanctionService.apply_sanction(
                case=case,
                sanctioned_student=sanctioned_student,
                applied_by=request.user,
                reason=reason,
            )
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect('accounts:dashboard')
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('cases:case-detail', case_id=case_id)

        request.session['sancion_modal'] = {
        'tipo': 'success',
        'mensaje': f'Sanción aplicada exitosamente. El caso fue reasignado a {sanctioned_student.user.name}.',
        }
        return redirect('cases:case-detail', case_id=case_id)

class StudentSanctionsHistoryView(LoginRequiredMixin, View):
    """
    PTCJMGA-XX: Vista de solo lectura del historial de sanciones de un estudiante.
    Cubre el Escenario 3 Gherkin de la HU.

    Solo profesores, coordinadores o admin pueden consultar.
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticacion requerida'}, status=401)

    def get(self, request, student_id):
        # Validar permisos (mismo criterio que aplicar sancion)
        if not request.user.is_superuser and not request.user.is_staff:
            user_role = getattr(request.user, 'role', None)
            if not user_role or user_role.name.lower() not in [
                'professor', 'profesor', 'admin', 'coordinator', 'coordinador'
            ]:
                messages.error(
                    request,
                    'No tiene permisos para consultar el historial de sanciones.'
                )
                return redirect('accounts:dashboard')

        # Buscar el estudiante
        from accounts.models import Student
        try:
            student = Student.objects.select_related('user').get(pk=student_id)
        except Student.DoesNotExist:
            messages.error(request, 'Estudiante no encontrado.')
            return redirect('accounts:dashboard')

        # Obtener sanciones del estudiante usando el servicio
        sanctions = SanctionService.get_student_sanctions(student)

        return render(request, 'cases/student_sanctions_history.html', {
            'student': student,
            'sanctions': sanctions,
            'sanctions_count': sanctions.count(),
            'page_title': f'Historial de sanciones - {student.user.name}',
        })
    
@login_required
def professor_notifications_count(request):
    """
    Retorna el conteo combinado de notificaciones para el profesor:
    - Casos con vencimiento crítico (≤ 7 días)
    - Reprogramaciones sin motivo (últimos 30 días)
    """
    if not _is_professor(request.user):
        return JsonResponse({'count': 0})

    try:
        professor = request.user.professor_profile
    except Exception:
        return JsonResponse({'count': 0})

    from datetime import timedelta

    # 1. Casos con vencimiento crítico (semáforo rojo o amarillo)
    today = timezone.now().date()
    deadline_count = Case.objects.filter(
        professor=professor,
        status__in=['active', 'Asignado', 'En proceso'],
        legal_deadline__lte=today + timedelta(days=7),
    ).count()

    # 2. Reprogramaciones sin motivo (últimos 30 días)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    reschedule_count = AppointmentLog.objects.filter(
        appointment__case__professor=professor,
        no_reason_flag=True,
        changed_at__gte=thirty_days_ago,
    ).count()

    return JsonResponse({'count': deadline_count + reschedule_count})
@login_required
def professor_inbox(request):
    """
    Bandeja de comunicaciones del profesor.
    Muestra todos los correos enviados en todos sus casos.
    """
    if not _is_professor(request.user):
        return redirect('accounts:dashboard')

    try:
        professor = request.user.professor_profile
    except Exception:
        return redirect('accounts:dashboard')

    # Todos los correos enviados por el profesor
    logs = CommunicationLog.objects.filter(
        sent_by=request.user,
    ).select_related('case__room').order_by('-sent_at')

    # Casos activos del profesor para el selector de redacción
    cases = Case.objects.filter(
        professor=professor,
        status__in=['active', 'Asignado', 'En proceso'],
    ).select_related('room').order_by('room__name')

    return render(request, 'cases/professor_inbox.html', {
        'logs':  logs,
        'cases': cases,
    })

@login_required
def secretary_reminders_dashboard(request):
    """
    Panel de la secretaria para monitorear el estado
    de los recordatorios automáticos de citas.
    """
    from datetime import timedelta
    from cases.models import CaseLog

    user_role = getattr(request.user, 'role', None)
    role_name = user_role.name.lower() if user_role else ''
    if role_name not in ['secretaria', 'secretary']:
        return redirect('accounts:dashboard')

    now    = timezone.now()
    window = now + timedelta(hours=24)

    # Citas próximas en las siguientes 24 horas
    upcoming = Appointment.objects.filter(
        scheduled_datetime__gte=now,
        scheduled_datetime__lte=window,
    ).exclude(
        status__in=['cancelada', 'completada']
    ).select_related(
        'case__beneficiary',
        'case__room',
        'case__student__user',
    ).order_by('scheduled_datetime')

    # Citas sin correo de beneficiario
    no_email = [a for a in upcoming if not a.case.beneficiary or not a.case.beneficiary.email]

    # Citas con recordatorio ya enviado
    reminded = [a for a in upcoming if a.reminder_sent]

    # Citas pendientes de recordatorio
    pending = [a for a in upcoming if not a.reminder_sent and a not in no_email]

    # Últimos eventos de bitácora de recordatorios
    recent_logs = CaseLog.objects.filter(
        event_type='error_notificacion',
    ).select_related('case__room').order_by('-created_at')[:20]

    return render(request, 'cases/secretary_reminders_dashboard.html', {
        'upcoming':     upcoming,
        'no_email':     no_email,
        'reminded':     reminded,
        'pending':      pending,
        'recent_logs':  recent_logs,
        'now':          now,
    })
class StudentsListForSanctionsView(LoginRequiredMixin, View):
    """
    PTCJMGA-XX: Vista del listado de estudiantes para que el profesor
    seleccione cual quiere consultar/sancionar.
    Accesible desde el sidebar del profesor.
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticacion requerida'}, status=401)

    def get(self, request):
        # Validar permisos (mismo criterio que aplicar sancion)
        if not request.user.is_superuser and not request.user.is_staff:
            user_role = getattr(request.user, 'role', None)
            if not user_role or user_role.name.lower() not in [
                'professor', 'profesor', 'admin', 'coordinator', 'coordinador'
            ]:
                messages.error(
                    request,
                    'No tiene permisos para consultar sanciones academicas.'
                )
                return redirect('accounts:dashboard')

        # Obtener estudiantes y calcular conteo de sanciones manualmente
        # (evita problemas con related_names duplicados en el modelo Case)
        from accounts.models import Student

        all_students = Student.objects.select_related('user').order_by('user__name')

        students = []
        for student in all_students:
            sanctions_count = SanctionService.get_student_sanctions(student).count()
            students.append({
                'id': student.id,
                'name': student.user.name,
                'student_code': student.student_code,
                'semester': student.semester,
                'sanctions_count': sanctions_count,
            })

        return render(request, 'cases/sanctions_students_list.html', {
            'students': students,
            'page_title': 'Sanciones academicas',
            'user_name': request.user.name,
            'role_name': get_user_role(request.user),
        })
