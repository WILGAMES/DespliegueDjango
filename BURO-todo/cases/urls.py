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
    ProfessorStudentsForGradingView,
    assignment_criteria_view,
    update_assignment_criteria_view,
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
]