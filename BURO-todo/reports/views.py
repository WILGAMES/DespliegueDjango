import io
import csv
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.utils import validate_coordinator, get_user_role, normalize_role_name
from .models import AcademicReport
from .services import generate_and_save_report
from datetime import date

logger = logging.getLogger(__name__)


def _check_coordinator(user):
    try:
        validate_coordinator(user)
    except PermissionDenied:
        raise PermissionDenied('Solo coordinadores pueden acceder a esta sección.')


def _ctx(user, page_title):
    return {
        'page_title': page_title,
        'role_name': normalize_role_name(get_user_role(user)),
    }


@login_required
def report_list_view(request):
    _check_coordinator(request.user)
    reports = AcademicReport.objects.filter(status='completed').order_by('-generated_at')
    ctx = _ctx(request.user, 'Reportes académicos')
    ctx['reports'] = reports
    return render(request, 'reports/report_list.html', ctx)


@login_required
def report_generate_view(request):
    _check_coordinator(request.user)

    if request.method == 'POST':
        period_label = request.POST.get('period_label', '').strip()
        date_from_str = request.POST.get('date_from', '')
        date_to_str = request.POST.get('date_to', '')

        try:
            date_from = date.fromisoformat(date_from_str)
            date_to = date.fromisoformat(date_to_str)
        except ValueError:
            messages.error(request, 'Fechas inválidas. Usa el formato YYYY-MM-DD.')
            return redirect('reports:generate')

        if date_from > date_to:
            messages.error(request, 'La fecha de inicio debe ser anterior a la fecha de fin.')
            return redirect('reports:generate')

        if not period_label:
            period_label = f'{date_from} — {date_to}'

        report = generate_and_save_report(
            period_label=period_label,
            date_from=date_from,
            date_to=date_to,
            generated_by=request.user,
        )

        if report.report_data.get('summary', {}).get('total_cases', 0) == 0:
            messages.warning(request, 'No hay datos registrados para el periodo seleccionado.')

        return redirect('reports:detail', pk=report.pk)

    ctx = _ctx(request.user, 'Generar reporte')
    return render(request, 'reports/report_generate.html', ctx)


@login_required
def report_detail_view(request, pk):
    _check_coordinator(request.user)
    report = get_object_or_404(AcademicReport, pk=pk, status='completed')
    ctx = _ctx(request.user, f'Reporte — {report.period_label}')
    ctx['report'] = report
    return render(request, 'reports/report_detail.html', ctx)


@login_required
def report_export_pdf_view(request, pk):
    _check_coordinator(request.user)
    report = get_object_or_404(AcademicReport, pk=pk, status='completed')

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f'Reporte Académico — {report.period_label}', styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f'Periodo: {report.date_from} al {report.date_to}', styles['Normal']))
    elements.append(Paragraph(f'Generado: {report.generated_at.strftime("%Y-%m-%d %H:%M")}', styles['Normal']))
    if report.generated_by:
        elements.append(Paragraph(f'Por: {report.generated_by.name}', styles['Normal']))
    else:
        elements.append(Paragraph('Origen: Automático', styles['Normal']))
    elements.append(Spacer(1, 20))

    summary = report.report_data.get('summary', {})
    _dark = colors.HexColor('#1e293b')
    _light1 = colors.HexColor('#f8fafc')
    _light2 = colors.HexColor('#e2e8f0')
    _grid = colors.HexColor('#94a3b8')

    table_data = [
        ['Indicador', 'Valor'],
        ['Total casos', str(summary.get('total_cases', 0))],
        ['Casos activos', str(summary.get('active_cases', 0))],
        ['Casos cerrados', str(summary.get('closed_cases', 0))],
        ['Casos asignados', str(summary.get('assigned_cases', 0))],
        ['Carga promedio / estudiante', str(summary.get('avg_load_per_student', 0))],
        ['Tasa de resolución', f"{summary.get('resolution_rate', 0)}%"],
        ['Tasa de asignación', f"{summary.get('assignment_rate', 0)}%"],
        ['Acciones académicas registradas', str(summary.get('total_academic_actions', 0))],
        ['Nota promedio', str(summary.get('avg_grade', 0))],
    ]
    t = Table(table_data, colWidths=[300, 150])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _dark),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [_light1, _light2]),
        ('GRID', (0, 0), (-1, -1), 0.5, _grid),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)

    breakdown = report.report_data.get('breakdown_by_room', [])
    if breakdown:
        elements.append(Spacer(1, 20))
        elements.append(Paragraph('Desglose por sala jurídica', styles['Heading2']))
        room_data = [['Sala', 'Total', 'Activos', 'Cerrados']]
        for room in breakdown:
            room_data.append([
                room['room_name'],
                str(room['total_cases']),
                str(room['active_cases']),
                str(room['closed_cases']),
            ])
        rt = Table(room_data, colWidths=[200, 80, 80, 80])
        rt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), _dark),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [_light1, _light2]),
            ('GRID', (0, 0), (-1, -1), 0.5, _grid),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(rt)

    doc.build(elements)
    buffer.seek(0)

    safe_label = report.period_label.replace(' ', '_').replace('—', '-')
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reporte_{safe_label}_{report.date_from}.pdf"'
    return response


@login_required
def report_export_csv_view(request, pk):
    _check_coordinator(request.user)
    report = get_object_or_404(AcademicReport, pk=pk, status='completed')

    output = io.StringIO()
    writer = csv.writer(output)

    summary = report.report_data.get('summary', {})
    writer.writerow(['Reporte Académico', report.period_label])
    writer.writerow(['Periodo', f'{report.date_from} al {report.date_to}'])
    writer.writerow(['Generado', report.generated_at.strftime('%Y-%m-%d %H:%M')])
    writer.writerow([])
    writer.writerow(['Indicador', 'Valor'])
    for label, key in [
        ('Total casos', 'total_cases'),
        ('Casos activos', 'active_cases'),
        ('Casos cerrados', 'closed_cases'),
        ('Casos asignados', 'assigned_cases'),
        ('Carga promedio por estudiante', 'avg_load_per_student'),
        ('Tasa de resolución (%)', 'resolution_rate'),
        ('Tasa de asignación (%)', 'assignment_rate'),
        ('Acciones académicas registradas', 'total_academic_actions'),
        ('Nota promedio', 'avg_grade'),
    ]:
        writer.writerow([label, summary.get(key, 0)])

    breakdown = report.report_data.get('breakdown_by_room', [])
    if breakdown:
        writer.writerow([])
        writer.writerow(['Sala', 'Total casos', 'Casos activos', 'Casos cerrados'])
        for room in breakdown:
            writer.writerow([
                room['room_name'],
                room['total_cases'],
                room['active_cases'],
                room['closed_cases'],
            ])

    safe_label = report.period_label.replace(' ', '_').replace('—', '-')
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="reporte_{safe_label}_{report.date_from}.csv"'
    return response
