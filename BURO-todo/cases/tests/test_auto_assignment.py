from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import SystemUser, Role, Student, Professor, LegalRoom
from cases.models import Case, AutomaticAssignmentLog, AssignmentCriteriaConfig
from cases.services.student_assignment_service import assign_case_to_student


class AutomaticAssignmentTests(TestCase):
    def setUp(self):
        self.role_student = Role.objects.create(name='estudiante')
        self.role_professor = Role.objects.create(name='profesor')

        self.prof_user = SystemUser.objects.create_user(
            email='prof@example.com',
            password='test1234',
            name='Profesor Test',
        )
        self.prof_user.role = self.role_professor
        self.prof_user.save()
        self.professor = Professor.objects.create(user=self.prof_user)

        self.room_a = LegalRoom.objects.create(name='Sala A')
        self.room_b = LegalRoom.objects.create(name='Sala B')

        self.student_user_1 = SystemUser.objects.create_user(
            email='student1@example.com',
            password='test1234',
            name='Student One',
        )
        self.student_user_1.role = self.role_student
        self.student_user_1.room = self.room_a
        self.student_user_1.save()
        self.student_1 = Student.objects.create(
            user=self.student_user_1,
            semester=1,
            student_code='S000001',
        )

        self.student_user_2 = SystemUser.objects.create_user(
            email='student2@example.com',
            password='test1234',
            name='Student Two',
        )
        self.student_user_2.role = self.role_student
        self.student_user_2.room = self.room_a
        self.student_user_2.save()
        self.student_2 = Student.objects.create(
            user=self.student_user_2,
            semester=1,
            student_code='S000002',
        )

        self.student_user_3 = SystemUser.objects.create_user(
            email='student3@example.com',
            password='test1234',
            name='Student Three',
        )
        self.student_user_3.role = self.role_student
        self.student_user_3.room = self.room_b
        self.student_user_3.save()
        self.student_3 = Student.objects.create(
            user=self.student_user_3,
            semester=1,
            student_code='S000003',
        )

        self.student_user_inactive = SystemUser.objects.create_user(
            email='student4@example.com',
            password='test1234',
            name='Student Inactive',
        )
        self.student_user_inactive.role = self.role_student
        self.student_user_inactive.room = self.room_a
        self.student_user_inactive.save()
        self.student_inactive = Student.objects.create(
            user=self.student_user_inactive,
            semester=1,
            student_code='S000004',
            status='inactive',
        )

        self.student_user_dashboard = SystemUser.objects.create_user(
            email='student_dashboard@example.com',
            password='test1234',
            name='Student Dashboard',
        )
        self.student_user_dashboard.role = self.role_student
        self.student_user_dashboard.room = self.room_a
        self.student_user_dashboard.save()
        self.student_dashboard = Student.objects.create(
            user=self.student_user_dashboard,
            semester=1,
            student_code='S000005',
        )

        self.client = Client()

    def _create_case(self, student=None, room=None, status='Pendiente'):
        assigned_student = student.user if student is not None and status == 'Asignado' else None
        return Case.objects.create(
            number=f'CASE-{Case.objects.count() + 1}',
            description='Caso de prueba',
            professor=self.professor,
            room=room or self.room_a,
            legal_deadline=timezone.localdate() + timedelta(days=7),
            status=status,
            student=student,
            assigned_student=assigned_student,
        )

    def test_assigns_case_to_student_with_lowest_active_load(self):
        self._create_case(student=self.student_1, status='Asignado')
        pending_case = self._create_case(status='Pendiente')

        selected_student = assign_case_to_student(pending_case)

        self.assertIsNotNone(selected_student)
        self.assertEqual(selected_student, self.student_2)
        self.assertEqual(pending_case.student, self.student_2)
        self.assertEqual(pending_case.assigned_student, self.student_user_2)
        self.assertEqual(pending_case.status, 'Asignado')

    def test_resolves_tie_by_lower_student_id(self):
        # Both students have zero load and belong to the same room
        pending_case = self._create_case(status='Pendiente')

        selected_student = assign_case_to_student(pending_case)

        self.assertEqual(selected_student, self.student_1)
        self.assertEqual(pending_case.student, self.student_1)

    def test_active_case_count_increases_after_assignment(self):
        pending_case = self._create_case(status='Pendiente')

        assign_case_to_student(pending_case)

        self.student_1.refresh_from_db()
        self.assertEqual(self.student_1.get_active_cases_count(), 1)

    def test_does_not_assign_inactive_students(self):
        pending_case = self._create_case(status='Pendiente')
        self.student_1.status = 'inactive'
        self.student_1.save()
        self.student_user_2.room = self.room_b
        self.student_user_2.save()

        selected_student = assign_case_to_student(pending_case)

        self.assertIsNone(selected_student)
        self.assertTrue(
            AutomaticAssignmentLog.objects.filter(
                case=pending_case,
                student__isnull=True,
            ).exists()
        )

    def test_does_not_assign_students_from_other_room(self):
        self.student_user_1.room = self.room_b
        self.student_user_1.save()
        self.student_user_2.room = self.room_b
        self.student_user_2.save()
        self.student_inactive.status = 'inactive'
        self.student_inactive.save()

        case_for_other_room = self._create_case(status='Pendiente', room=self.room_a)

        selected_student = assign_case_to_student(case_for_other_room)

        self.assertIsNone(selected_student)
        self.assertTrue(
            AutomaticAssignmentLog.objects.filter(
                case=case_for_other_room,
                student__isnull=True,
            ).exists()
        )

    def test_dashboard_shows_correct_assigned_case_count(self):
        case_active = self._create_case(student=self.student_dashboard, status='Asignado')
        self._create_case(student=self.student_dashboard, status='Finalizado')

        self.client.login(email='student_dashboard@example.com', password='test1234')
        response = self.client.get(reverse('accounts:student-dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_assigned_cases'], 1)
        self.assertEqual(len(response.context['assigned_cases']), 1)
        self.assertEqual(response.context['assigned_cases'][0]['number'], case_active.number)

    def test_automatic_assignment_log_created_on_success(self):
        pending_case = self._create_case(status='Pendiente')

        assign_case_to_student(pending_case)

        log = AutomaticAssignmentLog.objects.filter(case=pending_case, student=self.student_1).first()
        self.assertIsNotNone(log)
        self.assertTrue(log.created_by_system)
        self.assertIn('caso asignado automáticamente', log.assignment_reason.lower())
