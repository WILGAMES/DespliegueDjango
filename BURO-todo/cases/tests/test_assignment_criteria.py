from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import SystemUser, Role, Student, Professor
from cases.models import Case, AssignmentCriteriaConfig, AssignmentCriteriaLog
from accounts.utils import auto_assign_cases


class AssignmentCriteriaTests(TestCase):
    def setUp(self):
        # Roles
        self.role_secretary = Role.objects.create(name='secretaria')
        self.role_prof = Role.objects.create(name='profesor')
        self.role_student = Role.objects.create(name='estudiante')

        # Users
        self.secretary = SystemUser.objects.create_user(email='sec@example.com', password='test1234', name='Sec')
        self.secretary.role = self.role_secretary
        self.secretary.save()

        self.other_user = SystemUser.objects.create_user(email='user@example.com', password='test1234', name='User')

        # Professors and students
        self.prof_user = SystemUser.objects.create_user(email='prof@example.com', password='test1234', name='Prof')
        self.prof_user.role = self.role_prof
        self.prof_user.save()
        self.prof = Professor.objects.create(user=self.prof_user)

        # students
        self.students = []
        for i in range(3):
            u = SystemUser.objects.create_user(email=f'st{i}@example.com', password='test1234', name=f'Student{i}')
            u.role = self.role_student
            u.save()
            s = Student.objects.create(user=u, semester=1, student_code=f'S{i}X')
            self.students.append(s)

        # Rooms
        from accounts.models import LegalRoom
        self.room_a = LegalRoom.objects.create(name='Sala A')
        self.room_b = LegalRoom.objects.create(name='Sala B')

        # Cases helper: create pending case with given professor and room
        self.deadline = timezone.localdate() + timedelta(days=7)

        # Client
        self.client = Client()

    def _create_case(self, professor, room, status='Pendiente', student=None):
        return Case.objects.create(
            number=f'CASE-{Case.objects.count()+1}',
            description='desc',
            professor=professor,
            room=room,
            legal_deadline=self.deadline,
            status=status,
            student=student,
        )

    def test_secretary_can_save_config_and_unauthorized_cannot(self):
        # Secretary logs in and posts config
        self.client.login(email='sec@example.com', password='test1234')
        url = reverse('cases:update-assignment-criteria')
        data = {
            'max_cases_per_professor': 2,
            'prioritize_same_room': 'on',
            'balance_workload': 'on',
            'active': 'on',
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)
        cfg = AssignmentCriteriaConfig.objects.order_by('-updated_at').first()
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.max_cases_per_professor, 2)

        # Unauthorized user (other_user) cannot save
        self.client.logout()
        self.client.login(email='user@example.com', password='test1234')
        resp2 = self.client.post(url, data, follow=True)
        # should redirect to dashboard or deny access
        self.assertNotEqual(resp2.status_code, 200)

    def test_only_one_active_configuration(self):
        cfg1 = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=1, active=True)
        cfg2 = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=5, active=False)

        # Activate cfg2 via view
        self.client.login(email='sec@example.com', password='test1234')
        url = reverse('cases:update-assignment-criteria')
        data = {
            'max_cases_per_professor': 5,
            'prioritize_same_room': '',
            'balance_workload': 'on',
            'active': 'on',
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)

        cfg1.refresh_from_db()
        cfg2.refresh_from_db()
        # There should be exactly one active config
        active_count = AssignmentCriteriaConfig.objects.filter(active=True).count()
        self.assertEqual(active_count, 1)

    def test_max_cases_per_professor_is_respected(self):
        # Create config with max 1 case per professor
        cfg = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=1, active=True)

        # professor already has one active (non-closed) case
        existing = self._create_case(self.prof, self.room_a, status='Asignado', student=self.students[0])

        # create a pending case for same professor
        pending = self._create_case(self.prof, self.room_a, status='Pendiente')

        # Run assignment
        assigned = auto_assign_cases(self.prof_user)

        # pending should be skipped because professor already at capacity
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'Pendiente')

    def test_balance_workload_assigns_minimum_load(self):
        # config active with balance_workload True
        cfg = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=10, balance_workload=True, active=True)

        # create loads: student0 has 2 active, student1 has 1, student2 has 0
        self._create_case(self.prof, self.room_a, status='Asignado', student=self.students[0])
        self._create_case(self.prof, self.room_a, status='Asignado', student=self.students[0])
        self._create_case(self.prof, self.room_a, status='Asignado', student=self.students[1])

        pending = self._create_case(self.prof, self.room_a, status='Pendiente')
        assigned = auto_assign_cases(self.prof_user)

        pending.refresh_from_db()
        # student2 (index 2) should be chosen as has minimal load
        self.assertIsNotNone(pending.student)
        self.assertEqual(pending.student, self.students[2])

    def test_prioritize_same_room_prefers_same_room(self):
        # config active with prioritize_same_room True
        cfg = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=10, prioritize_same_room=True, balance_workload=True, active=True)

        # student0 has a case in room_a; student1 has lower overall load but no case in room_a
        self._create_case(self.prof, self.room_a, status='Asignado', student=self.students[0])
        # student1 has zero cases

        pending = self._create_case(self.prof, self.room_a, status='Pendiente')
        assigned = auto_assign_cases(self.prof_user)

        pending.refresh_from_db()
        self.assertIsNotNone(pending.student)
        # should choose student0 because of same-room prioritization
        self.assertEqual(pending.student, self.students[0])

    def test_modification_generates_logs_and_logs_immutable(self):
        cfg = AssignmentCriteriaConfig.objects.create(max_cases_per_professor=2, prioritize_same_room=False, balance_workload=False, active=True)
        self.client.login(email='sec@example.com', password='test1234')
        url = reverse('cases:update-assignment-criteria')
        data = {
            'max_cases_per_professor': 3,
            'prioritize_same_room': 'on',
            'balance_workload': '',
            'active': 'on',
        }
        resp = self.client.post(url, data, follow=True)
        self.assertEqual(resp.status_code, 200)

        logs = AssignmentCriteriaLog.objects.filter(criteria__max_cases_per_professor=3)
        # At least one log entry should exist for the max_cases_per_professor change
        self.assertTrue(logs.exists())

        # Ensure logs are not removed or altered by another update
        old_logs = list(AssignmentCriteriaLog.objects.all())
        # Perform a no-op update (same values)
        resp2 = self.client.post(url, data, follow=True)
        self.assertEqual(resp2.status_code, 200)
        new_logs = list(AssignmentCriteriaLog.objects.all())
        self.assertEqual(len(old_logs), len(new_logs))

