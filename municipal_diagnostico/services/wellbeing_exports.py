from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from municipal_diagnostico.models import BienestarPregunta
from municipal_diagnostico.services.exports import (
    EXCEL_THEME,
    PDF_THEME,
    WORD_THEME,
    _docx_header_row,
    _docx_page_break,
    _docx_paragraph,
    _docx_table,
    _package_docx,
)
from municipal_diagnostico.services.wellbeing import build_wellbeing_dashboard_summary


THIN_SIDE = Side(style="thin", color=EXCEL_THEME["line"])
THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
WRAP_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
CENTER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)


def build_wellbeing_pdf(*, public_url: str | None = None) -> BytesIO:
    summary = build_wellbeing_dashboard_summary()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "WellbeingTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=PDF_THEME["navy"],
        spaceAfter=10,
    )
    subtitle_style = ParagraphStyle(
        "WellbeingSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=PDF_THEME["muted"],
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "WellbeingSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=PDF_THEME["navy"],
        spaceBefore=10,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "WellbeingBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=PDF_THEME["muted"],
    )

    story = [
        Paragraph("Reporte ejecutivo de bienestar institucional", title_style),
        Paragraph(
            "Módulo complementario para captura anónima, seguimiento operativo y consolidación institucional.",
            subtitle_style,
        ),
    ]
    if public_url:
        story.append(Paragraph(f"Liga pública de respuesta: {public_url}", subtitle_style))

    metrics_rows = [
        ["Indicador", "Valor"],
        ["Total de sesiones", str(summary["total"])],
        ["Encuestas completadas", str(summary["completadas"])],
        ["Encuestas en progreso", str(summary["en_progreso"])],
        ["Encuestas abandonadas", str(summary["abandonadas"])],
        ["IIBP promedio", str(summary["avg_iibp"])],
        ["IVSP promedio", str(summary["avg_ivsp"])],
        ["Tasa de finalización", f'{summary["completion_rate"]}%'],
    ]
    story.append(Paragraph("Resumen general", section_style))
    story.append(_pdf_table(metrics_rows, [220, 220], header_fill=PDF_THEME["navy"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Promedio por dimensión", section_style))
    dimension_rows = [["Dimensión", "Promedio", "Puntaje", "Respuestas"]]
    for row in summary["dimensions"]:
        dimension_rows.append([row["name"], str(row["average"]), f'{row["percent"]}%', str(row["count"])])
    if len(dimension_rows) == 1:
        dimension_rows.append(["Sin datos", "-", "-", "-"])
    story.append(_pdf_table(dimension_rows, [230, 70, 70, 70], header_fill=PDF_THEME["sage"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Distribución por estrato", section_style))
    strata_rows = [["Estrato", "Encuestas completadas"]]
    for estrato, total in summary["strata_counts"].items():
        strata_rows.append([estrato, str(total)])
    story.append(_pdf_table(strata_rows, [180, 180], header_fill=PDF_THEME["sage"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Historial de sesiones", section_style))
    history_rows = [["Folio", "Fecha", "Estrato", "Estado", "Últ. pregunta", "IIBP", "IVSP"]]
    for row in summary["history"][:30]:
        history_rows.append(
            [
                row["hash"],
                row["fecha"],
                row["estrato"],
                row["estado_label"],
                str(row["ultima_pregunta"]),
                str(row["iibp"] if row["iibp"] is not None else "-"),
                str(row["ivsp"] if row["ivsp"] is not None else "-"),
            ]
        )
    if len(history_rows) == 1:
        history_rows.append(["Sin datos", "-", "-", "-", "-", "-", "-"])
    story.append(_pdf_table(history_rows, [70, 90, 45, 70, 55, 45, 45], header_fill=PDF_THEME["navy_soft"]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "El historial mostrado en PDF incluye hasta 30 sesiones recientes. El detalle completo permanece disponible en Excel y CSV.",
            body_style,
        )
    )

    document.build(story)
    buffer.seek(0)
    return buffer


def build_wellbeing_excel(*, public_url: str | None = None) -> BytesIO:
    summary = build_wellbeing_dashboard_summary()
    questions = BienestarPregunta.query.order_by(BienestarPregunta.orden.asc()).all()
    workbook = Workbook()

    summary_sheet = workbook.active
    summary_sheet.title = "Resumen"
    _write_title(summary_sheet, "Reporte ejecutivo de bienestar institucional", "Consolidado general", 4)
    summary_sheet.append([])
    summary_sheet.append(["Indicador", "Valor"])
    summary_sheet.append(["Total de sesiones", summary["total"]])
    summary_sheet.append(["Encuestas completadas", summary["completadas"]])
    summary_sheet.append(["Encuestas en progreso", summary["en_progreso"]])
    summary_sheet.append(["Encuestas abandonadas", summary["abandonadas"]])
    summary_sheet.append(["IIBP promedio", summary["avg_iibp"]])
    summary_sheet.append(["IVSP promedio", summary["avg_ivsp"]])
    summary_sheet.append(["Tasa de finalización", summary["completion_rate"]])
    if public_url:
        summary_sheet.append(["Liga pública", public_url])
    _style_table(summary_sheet, header_row=3)
    _set_widths(summary_sheet, {"A": 28, "B": 42})

    dimensions_sheet = workbook.create_sheet("Dimensiones")
    dimensions_sheet.append(["Dimensión", "Promedio", "Puntaje", "Respuestas"])
    for row in summary["dimensions"]:
        dimensions_sheet.append([row["name"], row["average"], row["percent"], row["count"]])
    _style_table(dimensions_sheet, header_row=1)
    _set_widths(dimensions_sheet, {"A": 34, "B": 12, "C": 12, "D": 12})

    history_sheet = workbook.create_sheet("Historial")
    history_sheet.append(["Folio", "Fecha", "Estrato", "Estado", "Última pregunta", "IIBP", "IVSP"])
    for row in summary["history"]:
        history_sheet.append(
            [
                row["hash"],
                row["fecha"],
                row["estrato"],
                row["estado_label"],
                row["ultima_pregunta"],
                row["iibp"] if row["iibp"] is not None else "",
                row["ivsp"] if row["ivsp"] is not None else "",
            ]
        )
    _style_table(history_sheet, header_row=1)
    _set_widths(history_sheet, {"A": 16, "B": 22, "C": 10, "D": 16, "E": 16, "F": 12, "G": 12})

    answers_sheet = workbook.create_sheet("Respuestas")
    answer_header = ["Folio", "Estrato", "Estado"]
    answer_header.extend([f"P{question.orden}" for question in questions])
    answers_sheet.append(answer_header)
    question_id_to_order = {question.id: question.orden for question in questions}
    for row in summary["history"]:
        response_values = [""] * len(questions)
        for question_id, value in row["respuestas"].items():
            order = question_id_to_order.get(question_id)
            if order:
                response_values[order - 1] = value
        answers_sheet.append([row["hash"], row["estrato"], row["estado_label"], *response_values])
    _style_table(answers_sheet, header_row=1)
    widths = {"A": 16, "B": 10, "C": 16}
    for index in range(4, len(answer_header) + 1):
        widths[_column_letter(index)] = 8
    _set_widths(answers_sheet, widths)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def build_wellbeing_word(*, public_url: str | None = None) -> BytesIO:
    summary = build_wellbeing_dashboard_summary()
    body = [
        _docx_paragraph("Reporte ejecutivo de bienestar institucional", bold=True, size=32, spacing_after=120),
        _docx_paragraph(
            "Módulo complementario para captura anónima, seguimiento operativo y consolidación institucional.",
            size=20,
            color=WORD_THEME["muted"],
        ),
    ]
    if public_url:
        body.append(_docx_paragraph(f"Liga pública de respuesta: {public_url}", size=18, color=WORD_THEME["muted"]))

    body.append(_docx_paragraph("Resumen general", bold=True, size=24, spacing_before=80))
    body.append(
        _docx_table(
            [
                _docx_header_row(["Indicador", "Valor"]),
                ["Total de sesiones", str(summary["total"])],
                ["Encuestas completadas", str(summary["completadas"])],
                ["Encuestas en progreso", str(summary["en_progreso"])],
                ["Encuestas abandonadas", str(summary["abandonadas"])],
                ["IIBP promedio", str(summary["avg_iibp"])],
                ["IVSP promedio", str(summary["avg_ivsp"])],
                ["Tasa de finalización", f'{summary["completion_rate"]}%'],
            ],
            col_widths=[4200, 2200],
        )
    )

    body.append(_docx_paragraph("", size=4, spacing_after=80))
    body.append(_docx_paragraph("Promedio por dimensión", bold=True, size=24))
    dimension_rows = [_docx_header_row(["Dimensión", "Promedio", "Puntaje", "Respuestas"])]
    for row in summary["dimensions"]:
        dimension_rows.append([row["name"], str(row["average"]), f'{row["percent"]}%', str(row["count"])])
    if len(dimension_rows) == 1:
        dimension_rows.append(["Sin datos", "-", "-", "-"])
    body.append(_docx_table(dimension_rows, col_widths=[3600, 1200, 1200, 1200]))

    body.append(_docx_paragraph("", size=4, spacing_after=80))
    body.append(_docx_paragraph("Distribución por estrato", bold=True, size=24))
    strata_rows = [_docx_header_row(["Estrato", "Encuestas completadas"])]
    for estrato, total in summary["strata_counts"].items():
        strata_rows.append([estrato, str(total)])
    body.append(_docx_table(strata_rows, col_widths=[2400, 2400]))

    body.append(_docx_page_break())
    body.append(_docx_paragraph("Historial de sesiones", bold=True, size=24))
    history_rows = [_docx_header_row(["Folio", "Fecha", "Estrato", "Estado", "Últ. pregunta", "IIBP", "IVSP"])]
    for row in summary["history"][:40]:
        history_rows.append(
            [
                row["hash"],
                row["fecha"],
                row["estrato"],
                row["estado_label"],
                str(row["ultima_pregunta"]),
                str(row["iibp"] if row["iibp"] is not None else "-"),
                str(row["ivsp"] if row["ivsp"] is not None else "-"),
            ]
        )
    if len(history_rows) == 1:
        history_rows.append(["Sin datos", "-", "-", "-", "-", "-", "-"])
    body.append(_docx_table(history_rows, col_widths=[1400, 1800, 1000, 1400, 1200, 900, 900]))
    body.append(
        _docx_paragraph(
            "El historial mostrado en Word incluye hasta 40 sesiones recientes. Para detalle completo utiliza Excel o CSV.",
            size=18,
            color=WORD_THEME["muted"],
            spacing_before=50,
        )
    )

    return _package_docx("".join(body), title="Reporte ejecutivo de bienestar institucional")


def _pdf_table(rows: list[list[str]], widths: list[int], *, header_fill) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_fill),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if header_fill != PDF_THEME["navy_soft"] else PDF_THEME["navy"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PDF_THEME["navy_soft"]]),
                ("GRID", (0, 0), (-1, -1), 0.5, PDF_THEME["line"]),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _write_title(sheet, title: str, subtitle: str, end_column: int) -> None:
    sheet.append([title])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
    sheet["A1"].font = Font(bold=True, size=16, color=EXCEL_THEME["navy"])
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.append([subtitle])
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_column)
    sheet["A2"].font = Font(size=11, color=EXCEL_THEME["muted"])
    sheet["A2"].alignment = Alignment(horizontal="center", vertical="center")


def _style_table(sheet, *, header_row: int) -> None:
    header_fill = PatternFill("solid", fgColor=EXCEL_THEME["navy"])
    zebra_fill = PatternFill("solid", fgColor=EXCEL_THEME["navy_soft"])
    for row in sheet.iter_rows():
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = WRAP_ALIGNMENT
    for cell in sheet[header_row]:
        cell.font = Font(bold=True, color=EXCEL_THEME["white"])
        cell.fill = header_fill
        cell.alignment = CENTER_ALIGNMENT
    for row_index in range(header_row + 1, sheet.max_row + 1):
        if row_index % 2 == 0:
            for cell in sheet[row_index]:
                cell.fill = zebra_fill


def _set_widths(sheet, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
