"""
PTCJMGA-50: Servicio de generacion de reportes legales para entidades gubernamentales.
Ley 2113 de 2021.

Filtra casos cerrados, detecta datos incompletos y genera PDF profesional con reportlab.
"""

from io import BytesIO
from datetime import date, datetime

from django.db.models import Q
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from cases.models import Case


# Campos obligatorios que deben estar completos en un caso cerrado
REQUIRED_FIELDS = ['number', 'beneficiary', 'student', 'room', 'professor']


class LegalReportGenerator:
    """
    Genera reportes legales en PDF a partir de casos cerrados.

    Uso:
        generator = LegalReportGenerator(date_from=date(2026,1,1), date_to=date.today())
        cases = generator.get_closed_cases()
        incomplete = generator.detect_incomplete_cases(cases)
        pdf_buffer = generator.generate_pdf(cases, secretary_name='Juliana')
    """

    def __init__(self, date_from=None, date_to=None):
        self.date_from = date_from
        self.date_to = date_to

    def get_closed_cases(self):
        """Retorna queryset de casos cerrados filtrados por rango de fechas."""
        queryset = Case.objects.filter(status='Cerrado').select_related(
            'beneficiary', 'student__user', 'professor__user', 'room'
        ).order_by('-created_at')

        if self.date_from:
            queryset = queryset.filter(created_at__date__gte=self.date_from)
        if self.date_to:
            queryset = queryset.filter(created_at__date__lte=self.date_to)

        return queryset

    def detect_incomplete_cases(self, cases_queryset):
        """Retorna lista de casos con campos obligatorios vacios o nulos."""
        incomplete = []
        for case in cases_queryset:
            missing = []
            if not case.number:
                missing.append('numero')
            if not case.beneficiary:
                missing.append('beneficiario')
            if not case.student:
                missing.append('estudiante')
            if not case.room:
                missing.append('sala')
            if not case.professor:
                missing.append('profesor')

            if missing:
                incomplete.append({
                    'case_id': case.id,
                    'case_number': case.number or f'(sin numero, ID={case.id})',
                    'missing_fields': missing,
                })
        return incomplete

    def generate_pdf(self, cases_queryset, secretary_name='Sistema BURO'):
        """
        Genera un PDF profesional con los casos provistos.
        Retorna un BytesIO listo para enviar como HttpResponse.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
            title='Reporte Legal Consultorio Juridico BURO',
            author=secretary_name,
        )

        # Metadata del reporte
        story = []
        styles = self._get_styles()

        # Header con titulo
        story.append(Paragraph('CONSULTORIO JURIDICO BURO', styles['header_main']))
        story.append(Paragraph('Universidad ICESI', styles['header_sub']))
        story.append(Spacer(1, 0.3*cm))
        story.append(Paragraph(
            'Reporte Legal para Entidades Gubernamentales',
            styles['title']
        ))
        story.append(Paragraph(
            'Ley 2113 de 2021 - Ley 1581 de 2012 (Habeas Data)',
            styles['subtitle']
        ))
        story.append(Spacer(1, 0.5*cm))

        # Metadata del filtro
        meta_data = [
            ['Generado por:', secretary_name],
            ['Fecha de generacion:', datetime.now().strftime('%d/%m/%Y %H:%M')],
            ['Fecha desde:', self.date_from.strftime('%d/%m/%Y') if self.date_from else 'Sin filtro'],
            ['Fecha hasta:', self.date_to.strftime('%d/%m/%Y') if self.date_to else 'Sin filtro'],
            ['Total casos cerrados:', str(cases_queryset.count())],
        ]
        meta_table = Table(meta_data, colWidths=[5*cm, 8*cm])
        meta_table.setStyle(TableStyle([
            ('FONTNAME',   (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME',   (1,0), (1,-1), 'Helvetica'),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('TEXTCOLOR',  (0,0), (-1,-1), colors.HexColor('#333333')),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F0F0F5')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 0.7*cm))

        # Titulo de tabla
        story.append(Paragraph('Casos Cerrados', styles['section']))
        story.append(Spacer(1, 0.2*cm))

        # Tabla de casos
        if cases_queryset.exists():
            story.append(self._build_cases_table(cases_queryset))
        else:
            story.append(Paragraph(
                'No se encontraron casos cerrados en el rango de fechas seleccionado.',
                styles['empty_state']
            ))

        # Footer note
        story.append(Spacer(1, 0.7*cm))
        story.append(Paragraph(
            'Este reporte fue generado automaticamente por el sistema BURO. '
            'La informacion contenida es confidencial y debe ser tratada conforme '
            'a la Ley 1581 de 2012 sobre proteccion de datos personales.',
            styles['footer_note']
        ))

        # Generar PDF
        doc.build(story, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        buffer.seek(0)
        return buffer

    def _build_cases_table(self, cases_queryset):
        """Construye la tabla principal con los casos."""
        # Encabezados
        data = [['#', 'Numero', 'Sala', 'Estudiante', 'Profesor', 'Fecha apertura']]

        for idx, case in enumerate(cases_queryset, start=1):
            student_name = case.student.user.name if case.student else '(sin asignar)'
            professor_name = case.professor.user.name if case.professor else '(sin asignar)'
            room_name = case.room.name if case.room else '(sin sala)'
            number = case.number or f'(ID {case.id})'
            created = case.created_at.strftime('%d/%m/%Y') if case.created_at else '-'

            data.append([
                str(idx),
                number,
                room_name,
                student_name,
                professor_name,
                created,
            ])

        table = Table(data, colWidths=[0.8*cm, 3.5*cm, 2.5*cm, 4*cm, 4*cm, 2.5*cm])
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND',  (0,0), (-1,0), colors.HexColor('#5454E9')),
            ('TEXTCOLOR',   (0,0), (-1,0), colors.white),
            ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,0), 10),
            ('ALIGN',       (0,0), (-1,0), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING',    (0,0), (-1,0), 8),
            # Cuerpo
            ('FONTNAME',  (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE',  (0,1), (-1,-1), 9),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#333333')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8F8FC')]),
            ('ALIGN',     (0,1), (0,-1), 'CENTER'),  # numero de fila
            ('VALIGN',    (0,0), (-1,-1), 'MIDDLE'),
            ('GRID',      (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
            ('LEFTPADDING',  (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING',   (0,1), (-1,-1), 6),
            ('BOTTOMPADDING',(0,1), (-1,-1), 6),
        ]))
        return table

    def _draw_footer(self, canvas, doc):
        """Dibuja el footer con numero de pagina en cada hoja."""
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#888888'))
        page_num = canvas.getPageNumber()
        text = f'Pagina {page_num}  |  BURO Consultorio Juridico ICESI  |  {datetime.now().strftime("%d/%m/%Y")}'
        canvas.drawCentredString(letter[0] / 2, 1*cm, text)
        canvas.restoreState()

    def _get_styles(self):
        """Estilos de texto reutilizables."""
        styles = getSampleStyleSheet()
        return {
            'header_main': ParagraphStyle(
                'HeaderMain',
                parent=styles['Title'],
                fontSize=18,
                textColor=colors.HexColor('#5454E9'),
                alignment=TA_CENTER,
                spaceAfter=2,
            ),
            'header_sub': ParagraphStyle(
                'HeaderSub',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#666666'),
                alignment=TA_CENTER,
                spaceAfter=8,
            ),
            'title': ParagraphStyle(
                'TitleReport',
                parent=styles['Heading1'],
                fontSize=14,
                textColor=colors.HexColor('#333333'),
                alignment=TA_CENTER,
                spaceAfter=2,
            ),
            'subtitle': ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#888888'),
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique',
            ),
            'section': ParagraphStyle(
                'Section',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#5454E9'),
                alignment=TA_LEFT,
            ),
            'empty_state': ParagraphStyle(
                'EmptyState',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#999999'),
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique',
            ),
            'footer_note': ParagraphStyle(
                'FooterNote',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.HexColor('#888888'),
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique',
            ),
        }