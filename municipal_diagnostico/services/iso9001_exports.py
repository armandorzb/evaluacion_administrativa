from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from municipal_diagnostico.services.iso9001 import summarize_iso9001_evaluation


EXCEL_COLORS = {
    "navy": "163042",
    "soft": "EEF2F5",
    "line": "D9E0E5",
    "white": "FFFFFF",
}


def build_iso9001_excel(evaluation) -> BytesIO:
    summary = summarize_iso9001_evaluation(evaluation)
    workbook = Workbook()

    resumen = workbook.active
    resumen.title = "Resumen"
    _write_title(resumen, "Diagnostico ISO 9001:2015", evaluation.dependencia.nombre, end_column=7)
    resumen.append([])
    resumen.append(["Estado", summary["state_label"]])
    resumen.append(["Avance", summary["completion"]])
    resumen.append(["Cumplimiento", summary["percent"] if summary["percent"] is not None else "Sin aplicables"])
    resumen.append(["Madurez", summary["maturity_label"]])
    resumen.append([])
    resumen.append(["Clausula", "Nombre", "Reactivos", "Respondidos", "Aplicables", "Pts.", "% Cumpl.", "Madurez"])
    header_row = resumen.max_row
    for clause in summary["clauses"]:
        resumen.append(
            [
                clause["numero"],
                clause["nombre"],
                clause["total"],
                clause["answered"],
                clause["applicable"],
                clause["points"],
                clause["percent"] if clause["percent"] is not None else "",
                clause["maturity_label"],
            ]
        )
    _style_table(resumen, header_row)
    _set_widths(resumen, {"A": 14, "B": 34, "C": 12, "D": 14, "E": 12, "F": 10, "G": 12, "H": 28})

    detalle = workbook.create_sheet("Cuestionario")
    _write_title(detalle, "Detalle de respuestas ISO 9001:2015", evaluation.ciclo.nombre, end_column=10)
    detalle.append([])
    detalle.append(
        [
            "Clausula",
            "Apartado",
            "N",
            "Reactivo",
            "Calificacion",
            "Pts.",
            "Observacion / hallazgo",
            "Evidencia sugerida",
            "Criterio de idoneidad",
            "Archivos",
        ]
    )
    detail_header = detalle.max_row
    for clause in summary["clauses"]:
        for section in clause["sections"]:
            for row in section["questions"]:
                reactive = row["reactivo"]
                detalle.append(
                    [
                        clause["numero"],
                        section["codigo"],
                        reactive.numero,
                        reactive.texto,
                        row["selected_label"],
                        "" if row["is_na"] or not row["answered"] else row["points"],
                        row["observacion"],
                        reactive.evidencia_sugerida,
                        reactive.criterio_idoneidad,
                        len(row["evidence"]),
                    ]
                )
    _style_table(detalle, detail_header)
    _set_widths(detalle, {"A": 10, "B": 12, "C": 8, "D": 50, "E": 15, "F": 8, "G": 36, "H": 36, "I": 44, "J": 10})

    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A4"

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def build_iso9001_pdf(evaluation) -> BytesIO:
    summary = summarize_iso9001_evaluation(evaluation)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Diagnostico ISO 9001:2015", styles["Title"]),
        Paragraph(f"Dependencia: {evaluation.dependencia.nombre}", styles["Normal"]),
        Paragraph(f"Ciclo: {evaluation.ciclo.nombre}", styles["Normal"]),
        Paragraph(f"Estado: {summary['state_label']}", styles["Normal"]),
        Spacer(1, 12),
    ]
    story.append(
        _table(
            [
                ["Avance", "Cumplimiento", "Madurez", "Evidencias"],
                [
                    f"{summary['completion']}%",
                    f"{summary['percent']}%" if summary["percent"] is not None else "Sin aplicables",
                    summary["maturity_label"],
                    str(summary["evidence_count"]),
                ],
            ],
            repeat_rows=1,
        )
    )
    story.append(Spacer(1, 14))
    story.append(Paragraph("Resultado por clausula", styles["Heading2"]))
    story.append(
        _table(
            [["Clausula", "Reactivos", "Respondidos", "Aplicables", "% Cumpl.", "Madurez"]]
            + [
                [
                    f"{clause['numero']} {clause['nombre']}",
                    clause["total"],
                    clause["answered"],
                    clause["applicable"],
                    f"{clause['percent']}%" if clause["percent"] is not None else "-",
                    clause["maturity_label"],
                ]
                for clause in summary["clauses"]
            ],
            repeat_rows=1,
        )
    )
    story.append(Spacer(1, 14))
    story.append(Paragraph("Hallazgos por apartado", styles["Heading2"]))
    section_rows = [["Apartado", "Respondidos", "Aplicables", "% Cumpl.", "Madurez"]]
    for section in summary["sections"]:
        section_rows.append(
            [
                f"{section['codigo']} {section['nombre']}",
                section["answered"],
                section["applicable"],
                f"{section['percent']}%" if section["percent"] is not None else "-",
                section["maturity_label"],
            ]
        )
    story.append(_table(section_rows, repeat_rows=1))
    doc.build(story)
    buffer.seek(0)
    return buffer


def _write_title(sheet, title: str, subtitle: str, *, end_column: int) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=18, color=EXCEL_COLORS["white"])
    sheet["A1"].fill = PatternFill("solid", fgColor=EXCEL_COLORS["navy"])
    sheet["A1"].alignment = Alignment(horizontal="center")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=end_column)
    sheet["A2"] = subtitle
    sheet["A2"].fill = PatternFill("solid", fgColor=EXCEL_COLORS["soft"])
    sheet["A2"].alignment = Alignment(horizontal="center")


def _style_table(sheet, header_row: int) -> None:
    border = Border(
        left=Side(style="thin", color=EXCEL_COLORS["line"]),
        right=Side(style="thin", color=EXCEL_COLORS["line"]),
        top=Side(style="thin", color=EXCEL_COLORS["line"]),
        bottom=Side(style="thin", color=EXCEL_COLORS["line"]),
    )
    for row in sheet.iter_rows(min_row=header_row, max_row=sheet.max_row):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row == header_row:
                cell.fill = PatternFill("solid", fgColor=EXCEL_COLORS["navy"])
                cell.font = Font(color=EXCEL_COLORS["white"], bold=True)


def _set_widths(sheet, widths: dict[str, int]) -> None:
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for row in range(1, sheet.max_row + 1):
        sheet.row_dimensions[row].height = 24


def _table(rows: list[list], repeat_rows: int = 0) -> Table:
    table = Table(rows, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163042")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E0E5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
            ]
        )
    )
    return table
