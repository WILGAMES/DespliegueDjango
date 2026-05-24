from datetime import date
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse


class BuildReportDataTest(TestCase):
    """Tests unitarios para _build_report_data (sin casos en BD = zeros)."""

    def test_empty_period_returns_zero_cases(self):
        from reports.services import _build_report_data
        data = _build_report_data(date(2020, 1, 1), date(2020, 1, 31))
        summary = data['summary']
        self.assertEqual(summary['total_cases'], 0)
        self.assertEqual(summary['active_cases'], 0)
        self.assertEqual(summary['closed_cases'], 0)

    def test_empty_period_returns_zero_rates(self):
        from reports.services import _build_report_data
        data = _build_report_data(date(2020, 1, 1), date(2020, 1, 31))
        summary = data['summary']
        self.assertEqual(summary['resolution_rate'], 0.0)
        self.assertEqual(summary['assignment_rate'], 0.0)
        self.assertEqual(summary['avg_grade'], 0.0)

    def test_empty_period_returns_breakdown_list(self):
        from reports.services import _build_report_data
        data = _build_report_data(date(2020, 1, 1), date(2020, 1, 31))
        self.assertIn('breakdown_by_room', data)
        self.assertIsInstance(data['breakdown_by_room'], list)

    def test_summary_has_all_required_keys(self):
        from reports.services import _build_report_data
        data = _build_report_data(date(2020, 1, 1), date(2020, 1, 31))
        required_keys = {
            'total_cases', 'active_cases', 'closed_cases', 'assigned_cases',
            'avg_load_per_student', 'resolution_rate', 'assignment_rate',
            'total_academic_actions', 'avg_grade',
        }
        self.assertTrue(required_keys.issubset(data['summary'].keys()))


class GenerateAndSaveReportTest(TestCase):
    """Tests de integración para generate_and_save_report."""

    def test_generates_completed_report(self):
        from reports.services import generate_and_save_report
        from reports.models import AcademicReport
        report = generate_and_save_report(
            period_label='2026-1',
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
        )
        self.assertEqual(report.status, 'completed')
        self.assertEqual(report.period_label, '2026-1')
        self.assertIn('summary', report.report_data)
        self.assertTrue(AcademicReport.objects.filter(pk=report.pk).exists())

    def test_manual_origin_by_default(self):
        from reports.services import generate_and_save_report
        report = generate_and_save_report(
            period_label='2026-1',
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
        )
        self.assertFalse(report.is_automatic)
        self.assertIsNone(report.generated_by)

    def test_automatic_flag_set_when_requested(self):
        from reports.services import generate_and_save_report
        report = generate_and_save_report(
            period_label='2026-auto',
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
            is_automatic=True,
        )
        self.assertTrue(report.is_automatic)

    def test_no_incomplete_report_saved_on_error(self):
        """HU2 criterio: si ocurre un error, no se almacena reporte incompleto."""
        from reports.services import generate_and_save_report
        from reports.models import AcademicReport

        with patch('reports.services._build_report_data', side_effect=RuntimeError('fallo simulado')):
            with self.assertRaises(RuntimeError):
                generate_and_save_report(
                    period_label='2026-error',
                    date_from=date(2026, 1, 1),
                    date_to=date(2026, 6, 30),
                    is_automatic=True,
                )

        self.assertFalse(AcademicReport.objects.filter(period_label='2026-error').exists())


class ReportViewsAccessTest(TestCase):
    """Tests de control de acceso a las vistas de reportes."""

    def setUp(self):
        from accounts.models import SystemUser, Role
        self.role_secretaria, _ = Role.objects.get_or_create(name='secretaria')
        self.coordinator = SystemUser.objects.create_user(
            email='coord@test.com',
            password='testpass123',
            name='Coordinadora Test',
        )
        self.coordinator.role = self.role_secretaria
        self.coordinator.save()

        self.other_user = SystemUser.objects.create_user(
            email='other@test.com',
            password='testpass123',
            name='Otro Usuario',
        )
        self.client = Client()

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('reports:list'))
        self.assertRedirects(response, f'/accounts/login/?next=/reports/')

    def test_coordinator_can_access_report_list(self):
        self.client.login(username='coord@test.com', password='testpass123')
        response = self.client.get(reverse('reports:list'))
        self.assertEqual(response.status_code, 200)

    def test_non_coordinator_gets_403(self):
        self.client.login(username='other@test.com', password='testpass123')
        response = self.client.get(reverse('reports:list'))
        self.assertEqual(response.status_code, 403)

    def test_coordinator_can_access_generate_form(self):
        self.client.login(username='coord@test.com', password='testpass123')
        response = self.client.get(reverse('reports:generate'))
        self.assertEqual(response.status_code, 200)

    def test_generate_post_creates_report_and_redirects(self):
        self.client.login(username='coord@test.com', password='testpass123')
        response = self.client.post(reverse('reports:generate'), {
            'period_label': 'Test-2026',
            'date_from': '2026-01-01',
            'date_to': '2026-06-30',
        })
        from reports.models import AcademicReport
        report = AcademicReport.objects.filter(period_label='Test-2026').first()
        self.assertIsNotNone(report)
        self.assertRedirects(response, reverse('reports:detail', kwargs={'pk': report.pk}))

    def test_generate_post_invalid_dates_shows_error(self):
        self.client.login(username='coord@test.com', password='testpass123')
        response = self.client.post(reverse('reports:generate'), {
            'period_label': 'Bad',
            'date_from': '2026-06-01',
            'date_to': '2026-01-01',  # fin antes que inicio
        })
        self.assertRedirects(response, reverse('reports:generate'))

    def test_detail_shows_no_data_message_for_empty_period(self):
        from reports.services import generate_and_save_report
        report = generate_and_save_report(
            period_label='Vacio',
            date_from=date(1990, 1, 1),
            date_to=date(1990, 1, 31),
            generated_by=self.coordinator,
        )
        self.client.login(username='coord@test.com', password='testpass123')
        response = self.client.get(reverse('reports:detail', kwargs={'pk': report.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay datos registrados')
