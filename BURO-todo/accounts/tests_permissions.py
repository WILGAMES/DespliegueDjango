"""
Tests for Permission and RolePermission models - TDD
Subtasks: PTCJMGA-110, PTCJMGA-111, PTCJMGA-112, PTCJMGA-158
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from accounts.utils import role_has_permission

from accounts.models import (
    SystemUser, Role, LegalRoom,
    Secretary, Student, Professor,
    Permission, RolePermission
)

class PermissionBaseTest(TestCase):

    def setUp(self):
        self.sala = LegalRoom.objects.create(name="Civil", description="Sala civil")

        self.role_secretary  = Role.objects.create(name="secretaria")
        self.role_professor  = Role.objects.create(name="profesor")
        self.role_student    = Role.objects.create(name="estudiante")
        self.role_admin      = Role.objects.create(name="administrador")

        self.perm_create_beneficiary = Permission.objects.create(
            resource="beneficiary", action="create"
        )
        self.perm_open_case = Permission.objects.create(
            resource="case", action="create"
        )
        self.perm_register_attendance = Permission.objects.create(
            resource="attendance", action="create"
        )
        self.perm_assign_case = Permission.objects.create(
            resource="case", action="assign"
        )
        self.perm_grade_student = Permission.objects.create(
            resource="student", action="grade"
        )

    def _create_user(self, email, role):
        return SystemUser.objects.create_user(
            email=email,
            name="Test User",
            password="Pass1234!",
            role=role,
            room=self.sala,
        )


# ─────────────────────────────────────────────
# PTCJMGA-110 · Permission model
# ─────────────────────────────────────────────

class TestPermissionModel(PermissionBaseTest):

    def test_permission_created_with_resource_and_action(self):
        """PTCJMGA-110: Permission is created with resource and action."""
        perm = Permission.objects.get(resource="beneficiary", action="create")
        self.assertIsNotNone(perm.pk)

    def test_permission_str(self):
        """PTCJMGA-110: Permission __str__ returns resource:action."""
        perm = Permission.objects.get(resource="beneficiary", action="create")
        self.assertEqual(str(perm), "beneficiary:create")

    def test_permission_unique_together(self):
        """PTCJMGA-110: Same resource+action cannot be duplicated."""
        with self.assertRaises(Exception):
            Permission.objects.create(resource="beneficiary", action="create")


# ─────────────────────────────────────────────
# PTCJMGA-110 · RolePermission model
# ─────────────────────────────────────────────

class TestRolePermissionModel(PermissionBaseTest):

    def test_assign_permission_to_role(self):
        """PTCJMGA-110: A permission can be assigned to a role."""
        rp = RolePermission.objects.create(
            role=self.role_secretary,
            permission=self.perm_create_beneficiary
        )
        self.assertIsNotNone(rp.pk)

    def test_role_can_have_multiple_permissions(self):
        """PTCJMGA-110: A role can have multiple permissions."""
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_create_beneficiary)
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_open_case)
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_register_attendance)
        count = RolePermission.objects.filter(role=self.role_secretary).count()
        self.assertEqual(count, 3)

    def test_same_role_permission_cannot_be_duplicated(self):
        """PTCJMGA-110: Same role+permission cannot be assigned twice."""
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_create_beneficiary)
        with self.assertRaises(Exception):
            RolePermission.objects.create(role=self.role_secretary, permission=self.perm_create_beneficiary)


# ─────────────────────────────────────────────
# PTCJMGA-158 · Secretary permissions
# ─────────────────────────────────────────────

class TestSecretaryPermissions(PermissionBaseTest):

    def setUp(self):
        super().setUp()
        # Assign secretary permissions
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_create_beneficiary)
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_open_case)
        RolePermission.objects.create(role=self.role_secretary, permission=self.perm_register_attendance)

    def test_secretary_has_create_beneficiary_permission(self):
        """PTCJMGA-158: Secretary can register beneficiaries."""
        has_perm = RolePermission.objects.filter(
            role=self.role_secretary,
            permission=self.perm_create_beneficiary
        ).exists()
        self.assertTrue(has_perm)

    def test_secretary_has_open_case_permission(self):
        """PTCJMGA-158: Secretary can open new cases."""
        has_perm = RolePermission.objects.filter(
            role=self.role_secretary,
            permission=self.perm_open_case
        ).exists()
        self.assertTrue(has_perm)

    def test_secretary_has_register_attendance_permission(self):
        """PTCJMGA-158: Secretary can register attendance."""
        has_perm = RolePermission.objects.filter(
            role=self.role_secretary,
            permission=self.perm_register_attendance
        ).exists()
        self.assertTrue(has_perm)

    def test_secretary_cannot_assign_cases(self):
        """PTCJMGA-158: Secretary cannot assign cases to students."""
        has_perm = RolePermission.objects.filter(
            role=self.role_secretary,
            permission=self.perm_assign_case
        ).exists()
        self.assertFalse(has_perm)

    def test_secretary_cannot_grade_students(self):
        """PTCJMGA-158: Secretary cannot grade students."""
        has_perm = RolePermission.objects.filter(
            role=self.role_secretary,
            permission=self.perm_grade_student
        ).exists()
        self.assertFalse(has_perm)

    def test_role_has_permission_helper(self):
        """PTCJMGA-158: Helper function checks role permissions correctly."""
        self.assertTrue(role_has_permission(self.role_secretary, "beneficiary", "create"))
        self.assertFalse(role_has_permission(self.role_secretary, "case", "assign"))


# ─────────────────────────────────────────────
# PTCJMGA-111/112 · Access control by role
# ─────────────────────────────────────────────

class TestAccessControlByRole(PermissionBaseTest):

    def setUp(self):
        super().setUp()
        self.client = Client()

        self.user_secretary = self._create_user("sec@icesi.edu.co", self.role_secretary)
        Secretary.objects.create(user=self.user_secretary)

        self.user_professor = self._create_user("prof@icesi.edu.co", self.role_professor)
        Professor.objects.create(user=self.user_professor)

        self.user_student = self._create_user("stu@icesi.edu.co", self.role_student)
        Student.objects.create(user=self.user_student)

        self.user_admin = self._create_user("admin@icesi.edu.co", self.role_admin)

    def test_secretary_can_access_secretary_register(self):
        """PTCJMGA-112: Secretary accesses secretary register endpoint."""
        self.client.login(username="sec@icesi.edu.co", password="Pass1234!")
        response = self.client.get(reverse("accounts:register_secretaria"))
        self.assertEqual(response.status_code, 200)

    def test_professor_cannot_access_secretary_register(self):
        """PTCJMGA-112: Professor receives 403 on secretary endpoint."""
        self.client.login(username="prof@icesi.edu.co", password="Pass1234!")
        response = self.client.get(reverse("accounts:register_secretaria"))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_secretary_register(self):
        """PTCJMGA-112: Student receives 403 on secretary endpoint."""
        self.client.login(username="stu@icesi.edu.co", password="Pass1234!")
        response = self.client.get(reverse("accounts:register_secretaria"))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected_from_secretary_register(self):
        """PTCJMGA-112: Unauthenticated user is redirected from secretary endpoint."""
        response = self.client.get(reverse("accounts:register_secretaria"))
        self.assertEqual(response.status_code, 302)


# ─────────────────────────────────────────────
# PTCJMGA-113 · Role change audit log
# ─────────────────────────────────────────────

class TestRoleChangeLog(PermissionBaseTest):

    def test_role_change_is_logged(self):
        """PTCJMGA-113: Changing a user's role creates an audit log entry."""
        from accounts.models import RoleChangeLog

        user = self._create_user("user@icesi.edu.co", self.role_student)
        RoleChangeLog.objects.create(
            user=user,
            old_role=self.role_student,
            new_role=self.role_secretary,
            changed_by=user,
        )
        log = RoleChangeLog.objects.filter(user=user).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.old_role.name, "estudiante")
        self.assertEqual(log.new_role.name, "secretaria")

    def test_log_records_who_made_the_change(self):
        """PTCJMGA-113: Audit log records which user made the change."""
        from accounts.models import RoleChangeLog

        admin = self._create_user("admin2@icesi.edu.co", self.role_admin)
        user  = self._create_user("user2@icesi.edu.co", self.role_student)
        RoleChangeLog.objects.create(
            user=user,
            old_role=self.role_student,
            new_role=self.role_professor,
            changed_by=admin,
        )
        log = RoleChangeLog.objects.filter(user=user).first()
        self.assertEqual(log.changed_by.email, "admin2@icesi.edu.co")


# ─────────────────────────────────────────────
# Helper function (goes in accounts/utils.py)
# ─────────────────────────────────────────────

def role_has_permission(role, resource, action):
    """
    Returns True if the given role has the specified permission.
    Usage: role_has_permission(user.role, 'beneficiary', 'create')
    """
    return RolePermission.objects.filter(
        role=role,
        permission__resource=resource,
        permission__action=action,
    ).exists()