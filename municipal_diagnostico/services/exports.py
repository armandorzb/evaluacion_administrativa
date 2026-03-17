from __future__ import annotations

import csv
from io import BytesIO, StringIO

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from municipal_diagnostico.services.analytics import summarize_evaluation, summarize_period


def build_evaluation_pdf(evaluacion) -> BytesIO:
    summary = summarize_evaluation(evaluacion)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#13293D"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#52606E"),
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#274C3A"),
        spaceBefore=14,
        spaceAfter=8,
    )

    story = [
        Table(
            [["Ayuntamiento de Hermosillo", "Diagnóstico Integral Municipal"]],
            colWidths=[2.2 * inch, 4.1 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#6E8B3D")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("PADDING", (0, 0), (-1, -1), 8),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            ),
        ),
        Spacer(1, 14),
        Paragraph("Reporte ejecutivo de evaluación", title_style),
        Paragraph(f"Dependencia: {evaluacion.dependencia.nombre}", subtitle_style),
        Paragraph(f"Periodo: {evaluacion.periodo.nombre}", subtitle_style),
        Paragraph(f"Estado: {summary['state_label']}", subtitle_style),
    ]

    if summary["is_preliminary"]:
        story.append(
            Paragraph(
                "Documento preliminar. La evaluación aún no forma parte del resultado oficial publicado.",
                ParagraphStyle(
                    "Warning",
                    parent=styles["Normal"],
                    fontName="Helvetica-Bold",
                    textColor=colors.HexColor("#8A5A00"),
                    backColor=colors.HexColor("#FFF2D9"),
                    borderPadding=7,
                    borderRadius=4,
                ),
            )
        )
        story.append(Spacer(1, 10))

    summary_table = Table(
        [
            ["Índice global", "Nivel", "Avance", "Ejes críticos"],
            [
                str(summary["index_score"]),
                summary["level_label"],
                f"{summary['completion']:.0f}%",
                str(len(summary["critical_axes"])),
            ],
        ],
        colWidths=[1.4 * inch, 1.4 * inch, 1.4 * inch, 1.5 * inch],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#13293D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F4F7F8")),
                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#13293D")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7E0EA")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_table)

    story.append(Paragraph("Desempeño por eje", section_style))
    axes_data = [["Eje", "Promedio", "Ponderación", "Brecha", "Prioridad", "Evidencias"]]
    for axis in summary["axes"]:
        axes_data.append(
            [
                axis["nombre"],
                axis["promedio"],
                f"{axis['ponderacion'] * 100:.0f}%",
                axis["brecha"],
                axis["prioridad"],
                axis["evidencias"],
            ]
        )
    axes_table = Table(axes_data, repeatRows=1, colWidths=[2.7 * inch, 0.7 * inch, 0.9 * inch, 0.7 * inch, 1.1 * inch, 0.8 * inch])
    axes_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEE8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#274C3A")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7E0EA")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFBFC")]),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(axes_table)

    story.append(Paragraph("Líneas de acción prioritarias", section_style))
    for axis in summary["axes_sorted"][:4]:
        story.append(
            Paragraph(
                f"<b>{axis['nombre']}:</b> {axis['recomendaciones'][0]}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 4))

    document.build(story)
    buffer.seek(0)
    return buffer


def build_period_excel(periodo, include_states=None) -> BytesIO:
    summary = summarize_period(periodo, include_states=include_states)
    workbook = Workbook()

    operational_sheet = workbook.active
    operational_sheet.title = "Avance Operativo"
    operational_sheet.append(
        ["Ranking", "Dependencia", "Estado", "Preliminar", "Índice", "Nivel", "Avance"]
    )
    for row in summary["operational_ranking"]:
        operational_sheet.append(
            [
                row["operational_rank"],
                row["dependencia"],
                row["estado_label"],
                "Sí" if row["is_preliminary"] else "No",
                row["indice"],
                row["nivel"],
                row["avance"],
            ]
        )

    official_sheet = workbook.create_sheet("Resultado Oficial")
    official_sheet.append(["Ranking", "Dependencia", "Estado", "Índice", "Nivel", "Avance"])
    for row in summary["official_ranking"]:
        official_sheet.append(
            [
                row["official_rank"],
                row["dependencia"],
                row["estado_label"],
                row["indice"],
                row["nivel"],
                row["avance"],
            ]
        )

    axis_sheet = workbook.create_sheet("Ejes")
    axis_sheet.append(
        ["Dependencia", "Estado", "Eje", "Promedio", "Ponderación", "Brecha", "Prioridad"]
    )
    for row in summary["operational_ranking"]:
        for axis in row["axes"]:
            axis_sheet.append(
                [
                    row["dependencia"],
                    row["estado_label"],
                    axis["nombre"],
                    axis["promedio"],
                    axis["ponderacion"],
                    axis["brecha"],
                    axis["prioridad"],
                ]
            )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def build_period_csv(periodo, include_states=None) -> BytesIO:
    summary = summarize_period(periodo, include_states=include_states)
    text = StringIO()
    writer = csv.writer(text)
    writer.writerow(
        [
            "ranking_operativo",
            "dependencia",
            "estado",
            "preliminar",
            "indice",
            "nivel",
            "avance",
        ]
    )
    for row in summary["operational_ranking"]:
        writer.writerow(
            [
                row["operational_rank"],
                row["dependencia"],
                row["estado_label"],
                "si" if row["is_preliminary"] else "no",
                row["indice"],
                row["nivel"],
                row["avance"],
            ]
        )
    payload = BytesIO(text.getvalue().encode("utf-8-sig"))
    payload.seek(0)
    return payload
