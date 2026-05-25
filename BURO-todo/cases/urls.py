from django.urls import path
from .views import (
    reschedule_appointment, 
    appointment_history,
    RegisterAcademicActionView,
    AcademicActionFormView,
    GetPartialGradeView,
    case_detail_view,
    case_list_view,
    CaseStatusUpdateView,
    StudentCasesView,
    StudentDeadlineSummaryView,
    ProfessorCasesView,
    ProfessorDeadlineSummaryView,
    ApplySanctionView,                  
    StudentSanctionsHistoryView,        
    ProfessorStudentsForGradingView,
    assignment_criteria_view,
    update_assignment_criteria_view,
    email_recipients,
    send_case_email,
    communication_history,
    compose_case_email,
    professor_appointment_alerts,
    professor_appointment_alerts_count,
    retry_failed_notification,
    professor_cases_page,
    professor_inbox,
    professor_notifications_count,
    secretary_reminders_dashboard,
    StudentsListForSanctionsView,
)

app_name = 'cases'

urlpatterns = [
    path(
        'academic-action/register/',
        RegisterAcademicActionView.as_view(),
        name='register-academic-action'
    ),
    path(
        'academic-action/form/<int:case_id>/',
        AcademicActionFormView.as_view(),
        name='academic-action-form'
    ),
        path(
        'academic-action/partial-grade/<int:case_id>/',
        GetPartialGradeView.as_view(),
        name='get-partial-grade'
    ),
    path('assignment-criteria/', assignment_criteria_view, name='assignment-criteria'),
    path('assignment-criteria/update/', update_assignment_criteria_view, name='update-assignment-criteria'),
    path('<int:case_id>/', case_detail_view, name='case-detail'),
    path('list/', case_list_view, name='case-list'),
    path('student-cases/', StudentCasesView.as_view(), name='student-cases'),
    path('student-deadline-summary/', StudentDeadlineSummaryView.as_view(), name='student-deadline-summary'),
    path('professor-cases/', ProfessorCasesView.as_view(), name='professor-cases'),
    path('professor-deadline-summary/', ProfessorDeadlineSummaryView.as_view(), name='professor-deadline-summary'),
    # Backend: Formulario de calificación de AcademicActionFormView (register_academic_action.html)
    # Frontend conexión: Lista de estudiantes del profesor para acceder al formulario
    path('professor-students-for-grading/', ProfessorStudentsForGradingView.as_view(), name='professor-students-for-grading'),
    path('academic-action/register/', RegisterAcademicActionView.as_view(), name='register-academic-action'),
    path('academic-action/form/<int:case_id>/', AcademicActionFormView.as_view(), name='academic-action-form'),
    path('academic-action/partial-grade/<int:case_id>/', GetPartialGradeView.as_view(), name='get-partial-grade'),
    path('case/<int:pk>/update-status/', CaseStatusUpdateView.as_view(), name='update-status'),
    path(
        'appointments/<int:appointment_id>/reschedule/',
        reschedule_appointment,
        name='reschedule_appointment',
    ),
    path(
        'appointments/<int:appointment_id>/history/',
        appointment_history,
        name='appointment_history',
    ),
    path(
        '<int:case_id>/email/recipients/',
        email_recipients,
        name='email_recipients',
    ),
    path(
        '<int:case_id>/email/send/',
        send_case_email,
        name='send_case_email',
    ),
    path(
        '<int:case_id>/email/history/',
        communication_history,
        name='communication_history',
    ),
    path(
        '<int:case_id>/email/compose/',
        compose_case_email,
        name='compose_case_email',
    ),
    path(
        'professor-alerts/',
        professor_appointment_alerts,
        name='professor_appointment_alerts',
    ),
    path(
        'professor-alerts/count/',
        professor_appointment_alerts_count,
        name='professor_appointment_alerts_count',
    ),
    path(
        '<int:case_id>/failed-notifications/<int:log_id>/retry/',
        retry_failed_notification,
        name='retry_failed_notification',
    ),
    path(
        'professor-cases/page/',
        professor_cases_page,
        name='professor_cases_page',
    ),
    
    # PTCJMGA-XX: Sancion academica
    path(
        '<int:case_id>/apply-sanction/',
        ApplySanctionView.as_view(),
        name='apply-sanction'
    ),
    path(
        'students/<int:student_id>/sanctions/',
        StudentSanctionsHistoryView.as_view(),
        name='student-sanctions-history'
    ),
    path(
    'professor-notifications/count/',
    professor_notifications_count,
    name='professor_notifications_count',
    ),
    path(
    'professor-inbox/',
    professor_inbox,
    name='professor_inbox',
    ),
    path(
    'secretary/reminders/',
    secretary_reminders_dashboard,
    name='secretary_reminders_dashboard'),
    # PTCJMGA-XX: Sanciones academicas - listado para sidebar del profesor
    path(
        'sanctions/students/',
        StudentsListForSanctionsView.as_view(),
        name='sanctions-list'
    ),
]