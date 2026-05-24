import json
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
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

        # Criterio 1: solo se pueden registrar acciones en casos activos
        if case.status != 'active':
            return JsonResponse({'error': 'No se pueden registrar acciones en casos cerrados o suspendidos'}, status=400)

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
    return redirect('cases:academic-action-form', case_id=case.id)


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

        # Validar que el caso esté activo
        if case.status != 'active':
            messages.error(request, 'No se pueden registrar acciones en casos no activos.')
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

        return render(request, 'cases/register_academic_action.html', {
            'case': case,
            'actions': actions,
            'page_title': 'Acción académica',
            'role_name': get_user_role(request.user),
            'academic_action_config': academic_action_config,
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
    cases = queryset.select_related('beneficiary').values('number', 'beneficiary__name', 'status')
    cases = list(cases)
    
    # Format the response
    response_data = [
        {
            "number": case['number'],
            "beneficiary": case['beneficiary__name'],
            "status": case['status']
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
    """
    HU: Como profesor asesor, quiero recibir alertas y ver en mi panel los casos
    de mi sala que se acercan a su fecha límite legal
    
    Criterio: Endpoint GET de casos de la sala con semáforo
    """

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        # Verificar rol del usuario
        if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name != 'PROFESSOR':
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

        # Obtener casos activos de la sala del profesor
        cases = Case.objects.filter(
            professor=professor,
            room=room,
            status='active'
        ).select_related('student__user', 'beneficiary').order_by('legal_deadline')

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
                'student_name': case.student.user.name if case.student else '',
                'days_remaining': days_remaining,
                'semaphore': semaphore,
            })

        # Ordenar: rojos primero, luego por días restantes
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
        if not hasattr(request.user, 'role') or request.user.role is None or request.user.role.name != 'PROFESSOR':
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
        
        # Obtener todos los casos activos del profesor (sin restricción a solo su sala)
        # El profesor puede tener casos en diferentes salas según su asignación
        cases = Case.objects.filter(
            professor=professor,
            status='active'
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
