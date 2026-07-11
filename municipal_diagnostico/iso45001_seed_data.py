"""Catalogo fijo del diagnostico ISO 45001:2018.

El contenido base se genero desde Matriz_Diagnostico_ISO_45001_2018.xlsx.
Se conserva dentro del codigo para que el catalogo sea autocontenido e inmutable
por version; no depende del archivo Excel en tiempo de ejecucion.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import json
import zlib


ISO45001_CATALOG_SLUG = "iso45001_2018_amd1_2024_diagnostico_v1"
ISO45001_V2_CATALOG_SLUG = "iso45001_2018_amd1_2024_diagnostico_v2_cobertura_documental"
ISO45001_SOURCE_REACTIVE_COUNT = 306
ISO45001_REACTIVE_COUNT = 308
ISO45001_DOCUMENT_COUNT = 31
ISO45001_CONTROL_EVIDENCE_COUNT = 37
ISO45001_NORMATIVE_CONTROL_COUNT = 31
ISO45001_COMPLEMENTARY_CONTROL_COUNT = 6

_CLAUSE_NAMES = {
    "4": "Contexto de la organizaci\u00f3n",
    "5": "Liderazgo y participaci\u00f3n de los trabajadores",
    "6": "Planificaci\u00f3n",
    "7": "Apoyo",
    "8": "Operaci\u00f3n",
    "9": "Evaluaci\u00f3n del desempe\u00f1o",
    "10": "Mejora",
}

# Los dos controles se anaden al catalogo base para incorporar ISO 45001:2018/Amd 1:2024.
ISO45001_AMD1_2024_REACTIVOS = (
    {
        "codigo": "R-307",
        "numero": 307,
        "clausula": "4",
        "apartado": "4.1",
        "tema": "Comprensi\u00f3n de la organizaci\u00f3n y de su contexto",
        "texto": (
            "\u00bfLa organizaci\u00f3n ha determinado si el cambio clim\u00e1tico es una cuesti\u00f3n "
            "pertinente para el contexto y los resultados previstos del SGSST?"
        ),
        "variable_principal": "Contexto",
        "criticidad": 2,
        "requiere_documento": False,
        "evidencia_sugerida": (
            "An\u00e1lisis de contexto actualizado; matriz PESTEL/FODA; acta de revisi\u00f3n."
        ),
        "criterio_idoneidad": (
            "La determinaci\u00f3n se integra a la revisi\u00f3n de cuestiones externas e internas, "
            "explica su pertinencia o no pertinencia y se revisa ante cambios relevantes."
        ),
        "es_enmienda_2024": True,
    },
    {
        "codigo": "R-308",
        "numero": 308,
        "clausula": "4",
        "apartado": "4.2",
        "tema": "Necesidades y expectativas de trabajadores y otras partes interesadas",
        "texto": (
            "\u00bfLa organizaci\u00f3n ha determinado si las partes interesadas pertinentes tienen "
            "requisitos relacionados con el cambio clim\u00e1tico y cu\u00e1les son aplicables al SGSST?"
        ),
        "variable_principal": "Partes interesadas",
        "criticidad": 2,
        "requiere_documento": False,
        "evidencia_sugerida": (
            "Matriz de partes interesadas y requisitos; an\u00e1lisis de requisitos legales y "
            "otros requisitos; minutas de consulta."
        ),
        "criterio_idoneidad": (
            "La matriz identifica los requisitos clim\u00e1ticos pertinentes de trabajadores y "
            "otras partes interesadas y define c\u00f3mo se consideran al planificar el SGSST."
        ),
        "es_enmienda_2024": True,
    },
)

# Carga compacta y estatica de los 306 reactivos y 31 documentos transcritos del Excel.
# No se consulta ni modifica ningun archivo externo al importar este modulo.
_SOURCE_PAYLOAD = (
    "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"
)

# El Excel marca estos 40 reactivos base como no documentales; los restantes 266
# requieren adjuntar evidencia al responder Parcial o Sí.
_ISO45001_BASE_REACTIVOS_SIN_DOCUMENTO = frozenset(
    {
        "R-001", "R-002", "R-003", "R-004", "R-005", "R-006", "R-020",
        "R-021", "R-022", "R-023", "R-024", "R-025", "R-026", "R-027",
        "R-028", "R-029", "R-030", "R-031", "R-032", "R-033", "R-034",
        "R-035", "R-036", "R-037", "R-129", "R-130", "R-131", "R-132",
        "R-133", "R-143", "R-144", "R-145", "R-146", "R-147", "R-148",
        "R-149", "R-283", "R-284", "R-285", "R-286",
    }
)


def _load_source_payload() -> dict:
    raw = zlib.decompress(base64.b64decode("".join(_SOURCE_PAYLOAD)))
    return json.loads(raw.decode("utf-8"))


def _document_applies_to_section(document_section: str, reactive_section: str) -> bool:
    return reactive_section == document_section or reactive_section.startswith(
        f"{document_section}."
    )


def _build_iso45001_version() -> dict:
    source = _load_source_payload()
    documents = [dict(item) for item in source["documentos"]]
    reactives = [dict(item) for item in source["reactivos"]]
    reactives.extend(dict(item) for item in ISO45001_AMD1_2024_REACTIVOS)

    documents_by_section = {}
    for document in documents:
        documents_by_section.setdefault(document["apartado"], []).append(document)

    for reactive in reactives:
        reactive.setdefault("es_enmienda_2024", False)
        if reactive["numero"] <= ISO45001_SOURCE_REACTIVE_COUNT:
            reactive["requiere_documento"] = (
                reactive["codigo"] not in _ISO45001_BASE_REACTIVOS_SIN_DOCUMENTO
            )
        reactive["documentos_requeridos"] = [
            document["codigo"]
            for document_section, section_documents in documents_by_section.items()
            if _document_applies_to_section(document_section, reactive["apartado"])
            for document in section_documents
        ]

    for document in documents:
        document["reactivos"] = [
            reactive["codigo"]
            for reactive in reactives
            if document["codigo"] in reactive["documentos_requeridos"]
        ]

    clauses_by_number: dict[str, dict] = {}
    for reactive in reactives:
        clause = clauses_by_number.setdefault(
            reactive["clausula"],
            {
                "numero": reactive["clausula"],
                "nombre": _CLAUSE_NAMES[reactive["clausula"]],
                "orden": int(reactive["clausula"]),
                "apartados": [],
            },
        )
        sections_by_code = {
            section["codigo"]: section for section in clause["apartados"]
        }
        section = sections_by_code.get(reactive["apartado"])
        if section is None:
            section = {
                "codigo": reactive["apartado"],
                "nombre": reactive["tema"],
                "orden": len(clause["apartados"]) + 1,
                "reactivos": [],
            }
            clause["apartados"].append(section)

        section["reactivos"].append(
            {
                "codigo": reactive["codigo"],
                "numero": reactive["numero"],
                "orden": len(section["reactivos"]) + 1,
                "tema": reactive["tema"],
                "texto": reactive["texto"],
                "variable_principal": reactive["variable_principal"],
                "criticidad": reactive["criticidad"],
                "requiere_documento": reactive["requiere_documento"],
                "documentos_requeridos": reactive["documentos_requeridos"],
                "evidencia_sugerida": reactive["evidencia_sugerida"],
                "criterio_idoneidad": reactive["criterio_idoneidad"],
                "es_enmienda_2024": reactive["es_enmienda_2024"],
            }
        )

    return {
        "slug": ISO45001_CATALOG_SLUG,
        "nombre": "Diagn\u00f3stico de implementaci\u00f3n ISO 45001:2018 + Amd. 1:2024",
        "descripcion": (
            "Cuestionario fijo para evaluar el Sistema de Gesti\u00f3n de Seguridad y Salud "
            "en el Trabajo (SGSST) conforme a ISO 45001:2018 y su enmienda clim\u00e1tica 2024."
        ),
        "norma": "ISO 45001:2018 + Amd. 1:2024",
        "aviso_diagnostico": (
            "Este resultado es un diagn\u00f3stico de preparaci\u00f3n; no constituye una certificaci\u00f3n "
            "ni sustituye la consulta de la norma autorizada o de la legislaci\u00f3n aplicable."
        ),
        "fuente": {
            "archivo": "Matriz_Diagnostico_ISO_45001_2018.xlsx",
            "reactivos_base": ISO45001_SOURCE_REACTIVE_COUNT,
            "enmienda": "ISO 45001:2018/Amd 1:2024",
        },
        "clausulas": [
            clauses_by_number[number] for number in sorted(clauses_by_number, key=int)
        ],
        "documentos_obligatorios": documents,
    }


def _validate_catalog(version: dict) -> None:
    reactives = [
        reactive
        for clause in version["clausulas"]
        for section in clause["apartados"]
        for reactive in section["reactivos"]
    ]
    amendment_codes = {
        reactive["codigo"] for reactive in reactives if reactive["es_enmienda_2024"]
    }
    section_codes = {
        section["codigo"]
        for clause in version["clausulas"]
        for section in clause["apartados"]
    }

    if len(reactives) != ISO45001_REACTIVE_COUNT:
        raise RuntimeError("El cat\u00e1logo ISO 45001 debe contener 308 reactivos.")
    if len(version["documentos_obligatorios"]) != ISO45001_DOCUMENT_COUNT:
        raise RuntimeError("El cat\u00e1logo ISO 45001 debe contener 31 documentos requeridos.")
    if section_codes != {
        "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "5.4",
        "6.1.1", "6.1.2.1", "6.1.2.2", "6.1.2.3", "6.1.3", "6.1.4",
        "6.2.1", "6.2.2", "7.1", "7.2", "7.3", "7.4.1", "7.4.2",
        "7.4.3", "7.5.1", "7.5.2", "7.5.3", "8.1.1", "8.1.2",
        "8.1.3", "8.1.4.1", "8.1.4.2", "8.1.4.3", "8.2", "9.1.1",
        "9.1.2", "9.2.1", "9.2.2", "9.3", "10.1", "10.2", "10.3",
    }:
        raise RuntimeError("El cat\u00e1logo ISO 45001 debe conservar sus 40 apartados.")
    if amendment_codes != {"R-307", "R-308"}:
        raise RuntimeError("Faltan los reactivos de ISO 45001:2018/Amd 1:2024.")


ISO45001_VERSION = _build_iso45001_version()
_validate_catalog(ISO45001_VERSION)


def _reactive_codes(*ranges: tuple[int, int]) -> tuple[str, ...]:
    """Return explicitly declared reactive codes for a coverage-matrix row.

    The ranges below are authored as part of the matrix.  This helper only
    renders their fixed numeric identifiers; it never infers coverage from an
    ISO clause prefix.
    """

    return tuple(
        f"R-{number:03d}"
        for start, end in ranges
        for number in range(start, end + 1)
    )


# Matriz documental v2: cada relación se declara de forma explícita.  Los
# solapamientos D-23/D-24, D-26/D-27 y D-29/D-30 son intencionales porque los
# documentos prueban aspectos distintos de los mismos reactivos.
ISO45001_V2_CONTROL_REACTIVE_CODES = {
    "D-01": _reactive_codes((14, 19)),
    "D-02": _reactive_codes((38, 45)),
    "D-03": _reactive_codes((46, 52)),
    "D-04": _reactive_codes((65, 70)),
    "D-05": _reactive_codes((85, 93)),
    "D-06": _reactive_codes((94, 99)),
    "D-07": _reactive_codes((100, 107)),
    "D-08": _reactive_codes((108, 114)),
    "D-09": _reactive_codes((115, 121)),
    "D-10": _reactive_codes((122, 128)),
    "D-11": _reactive_codes((134, 142)),
    "D-12": _reactive_codes((150, 155)),
    # D-13 se limita a 7.5.1; no absorbe creación, actualización ni control.
    "D-13": _reactive_codes((166, 170)),
    "D-14": _reactive_codes((171, 176)),
    "D-15": _reactive_codes((177, 185)),
    "D-16": _reactive_codes((186, 193)),
    "D-17": _reactive_codes((194, 202)),
    "D-18": _reactive_codes((203, 210)),
    "D-19": _reactive_codes((211, 216)),
    "D-20": _reactive_codes((217, 224)),
    "D-21": _reactive_codes((225, 230)),
    "D-22": _reactive_codes((231, 240)),
    "D-23": _reactive_codes((241, 247), (249, 250)),
    "D-24": _reactive_codes((248, 248), (250, 250)),
    "D-25": _reactive_codes((251, 257)),
    "D-26": _reactive_codes((263, 267), (270, 270)),
    "D-27": _reactive_codes((268, 270)),
    "D-28": _reactive_codes((271, 282)),
    "D-29": _reactive_codes((287, 288), (290, 292), (298, 298)),
    "D-30": _reactive_codes((289, 289), (293, 298)),
    "D-31": _reactive_codes((299, 306)),
    "G-01": _reactive_codes((7, 13)),
    "G-02": _reactive_codes((53, 64)),
    "G-03": _reactive_codes((71, 84)),
    "G-04": _reactive_codes((156, 160)),
    "G-05": _reactive_codes((161, 165)),
    "G-06": _reactive_codes((258, 262)),
}


# Puntos mínimos curados a partir del contenido mínimo del catálogo y de la
# evidencia esperada de los reactivos que cubre cada control.
ISO45001_V2_CONTROL_POINTS = {
    "D-01": (
        "Delimita unidades, centros, actividades y trabajadores incluidos.",
        "Identifica el control e influencia sobre actividades relacionadas.",
        "Está disponible para las partes interesadas pertinentes.",
    ),
    "D-02": (
        "Incluye los compromisos requeridos de seguridad y salud en el trabajo.",
        "Cuenta con aprobación de la alta dirección.",
        "Se comunica, permanece disponible y se revisa cuando corresponde.",
    ),
    "D-03": (
        "Asigna responsabilidades y autoridades de SST en los niveles pertinentes.",
        "Comunica las responsabilidades y autoridades asignadas.",
    ),
    "D-04": (
        "Identifica riesgos y oportunidades del SGSST.",
        "Define procesos o acciones para abordarlos.",
        "Conserva evidencia de la evaluación y seguimiento de las acciones.",
    ),
    "D-05": (
        "Define una metodología proactiva de evaluación de riesgos de SST.",
        "Establece criterios de evaluación consistentes.",
        "Conserva resultados trazables de la identificación y evaluación.",
    ),
    "D-06": (
        "Identifica oportunidades de SST.",
        "Prioriza oportunidades y asigna responsables.",
        "Conserva las decisiones tomadas sobre las oportunidades.",
    ),
    "D-07": (
        "Mantiene obligaciones legales y otros requisitos aplicables.",
        "Define responsables y el mecanismo de actualización.",
        "Demuestra cómo se aplican las obligaciones al SGSST.",
    ),
    "D-08": (
        "Define acciones para abordar riesgos, oportunidades y emergencias.",
        "Asigna responsables, plazos y recursos.",
        "Incluye indicadores o criterios para evaluar la eficacia.",
    ),
    "D-09": (
        "Define objetivos de SST coherentes con la política y riesgos.",
        "Los objetivos son medibles o evaluables.",
        "Los objetivos se comunican y actualizan cuando corresponde.",
    ),
    "D-10": (
        "Establece qué se hará para cada objetivo.",
        "Define recursos, responsables y plazos.",
        "Define evaluación e integración de los objetivos en los procesos.",
    ),
    "D-11": (
        "Conserva perfiles, formación y experiencia pertinentes.",
        "Conserva licencias o habilitaciones requeridas.",
        "Evalúa la eficacia de las acciones de competencia.",
    ),
    "D-12": (
        "Identifica emisor y destinatario de la comunicación.",
        "Conserva contenido y fecha de la comunicación.",
        "Mantiene respuesta y trazabilidad cuando procede.",
    ),
    "D-13": (
        "Define la arquitectura de información documentada necesaria para el SGSST.",
        "Mantiene un listado maestro acorde con riesgos y complejidad.",
    ),
    "D-14": (
        "Controla identificación y formato de documentos.",
        "Define revisión y aprobación antes de su uso.",
        "Controla cambios y versiones de la información documentada.",
    ),
    "D-15": (
        "Controla acceso y distribución de documentos y registros.",
        "Define almacenamiento y preservación de la información.",
        "Controla cambios, retención y disposición final.",
    ),
    "D-16": (
        "Define procedimientos, permisos o instructivos de control operacional.",
        "Conserva registros que demuestren el control operacional.",
    ),
    "D-17": (
        "Justifica la selección de controles conforme a la jerarquía de controles.",
        "Registra el riesgo residual y las necesidades de mantenimiento.",
        "Conserva evidencia de la eficacia de los controles.",
    ),
    "D-18": (
        "Evalúa cambios antes de implementarlos.",
        "Conserva aprobación y controles definidos para el cambio.",
        "Documenta comunicación y cierre de los cambios.",
    ),
    "D-19": (
        "Incluye requisitos de SST en especificaciones de compras.",
        "Conserva evaluación y recepción de productos o servicios.",
        "Mantiene controles de SST aplicables a las adquisiciones.",
    ),
    "D-20": (
        "Conserva precalificación e inducción de contratistas.",
        "Controla permisos y coordinación de actividades.",
        "Registra supervisión y desempeño de contratistas.",
    ),
    "D-21": (
        "Define tipo y grado de control sobre procesos externalizados.",
        "Establece obligaciones de SST en los acuerdos aplicables.",
        "Evalúa el desempeño de los procesos externalizados.",
    ),
    "D-22": (
        "Identifica escenarios y planes de emergencia.",
        "Define brigadas, recursos y comunicación de emergencia.",
        "Conserva pruebas, evaluación y mejora de la respuesta.",
    ),
    "D-23": (
        "Define indicadores, métodos y criterios de seguimiento y medición.",
        "Conserva resultados, análisis de tendencias y evaluación.",
        "Documenta decisiones derivadas de los resultados.",
    ),
    "D-24": (
        "Identifica equipos sujetos a calibración, verificación o mantenimiento.",
        "Conserva estado y trazabilidad de los equipos.",
        "Documenta resultados y acciones ante desviaciones.",
    ),
    "D-25": (
        "Evalúa el cumplimiento por cada obligación aplicable.",
        "Conserva evidencia y conclusión de la evaluación.",
        "Documenta acciones derivadas de incumplimientos o desviaciones.",
    ),
    "D-26": (
        "Define frecuencia, métodos y responsabilidades del programa de auditoría.",
        "Incluye consulta, planificación y seguimiento de auditorías.",
    ),
    "D-27": (
        "Conserva planes y evidencias de auditoría interna.",
        "Documenta hallazgos, informes y acciones resultantes.",
    ),
    "D-28": (
        "Conserva entradas de revisión por la dirección.",
        "Documenta decisiones sobre recursos, cambios y oportunidades.",
        "Asigna responsables a las decisiones resultantes.",
    ),
    "D-29": (
        "Registra naturaleza del incidente o no conformidad y reacción inmediata.",
        "Conserva investigación de causas y consecuencias.",
    ),
    "D-30": (
        "Define acciones correctivas, responsables y plazos.",
        "Conserva verificación de ejecución y evaluación de eficacia.",
    ),
    "D-31": (
        "Conserva proyectos o resultados de mejora continua.",
        "Documenta lecciones aprendidas, tendencias y estandarización.",
        "Comunica las mejoras relevantes.",
    ),
    "G-01": (
        "Identifica partes interesadas pertinentes para el SGSST.",
        "Determina necesidades, expectativas y requisitos aplicables.",
        "Revisa y comunica cambios relevantes en los requisitos.",
    ),
    "G-02": (
        "Define mecanismos de consulta y participación de trabajadores.",
        "Conserva evidencias de participación en decisiones de SST.",
        "Registra barreras, resultados y retroalimentación de la consulta.",
    ),
    "G-03": (
        "Identifica peligros de forma continua y proactiva.",
        "Considera personas, actividades, condiciones y cambios relevantes.",
        "Conserva resultados de la identificación de peligros y evaluación inicial.",
    ),
    "G-04": (
        "Define qué, cuándo y con quién se comunica internamente.",
        "Conserva evidencias de comunicación interna de SST.",
    ),
    "G-05": (
        "Define comunicaciones externas de SST pertinentes.",
        "Conserva evidencias de emisión, recepción y seguimiento cuando procede.",
    ),
    "G-06": (
        "Define criterios, alcance y proceso de auditoría interna.",
        "Conserva evidencia de competencia e independencia de auditores.",
        "Documenta la ejecución general y seguimiento del proceso de auditoría.",
    ),
}


ISO45001_V2_COMPLEMENTARY_CONTROL_SPECS = (
    {
        "codigo": "G-01",
        "clausula": "4",
        "apartado": "4.2",
        "nombre": "Partes interesadas y requisitos del SGSST",
        "contenido_minimo": (
            "Identificación de partes interesadas, necesidades y expectativas, requisitos "
            "aplicables, revisión y comunicación."
        ),
        "evidencia_sugerida": "Matriz de partes interesadas, requisitos aplicables y minutas de consulta.",
        "criticidad": 2,
    },
    {
        "codigo": "G-02",
        "clausula": "5",
        "apartado": "5.4",
        "nombre": "Consulta y participación de los trabajadores",
        "contenido_minimo": (
            "Mecanismos de consulta, participación, barreras, resultados y retroalimentación "
            "de los trabajadores."
        ),
        "evidencia_sugerida": "Actas de comités, listas de asistencia, encuestas y registros de consulta.",
        "criticidad": 3,
    },
    {
        "codigo": "G-03",
        "clausula": "6",
        "apartado": "6.1.2.1",
        "nombre": "Identificación de peligros e IPER",
        "contenido_minimo": (
            "Identificación continua y proactiva de peligros, personas, actividades, condiciones, "
            "cambios y resultados iniciales de evaluación."
        ),
        "evidencia_sugerida": "Matriz IPER, recorridos de seguridad y registros de identificación de peligros.",
        "criticidad": 3,
    },
    {
        "codigo": "G-04",
        "clausula": "7",
        "apartado": "7.4.2",
        "nombre": "Comunicación interna de SST",
        "contenido_minimo": "Plan, mensajes, destinatarios, fechas y evidencias de comunicación interna.",
        "evidencia_sugerida": "Comunicados, tableros, minutas, listas de asistencia y campañas internas.",
        "criticidad": 2,
    },
    {
        "codigo": "G-05",
        "clausula": "7",
        "apartado": "7.4.3",
        "nombre": "Comunicación externa de SST",
        "contenido_minimo": "Comunicaciones externas pertinentes, destinatarios, evidencia de emisión y seguimiento.",
        "evidencia_sugerida": "Oficios, reportes a autoridades, comunicaciones con contratistas y acuses.",
        "criticidad": 2,
    },
    {
        "codigo": "G-06",
        "clausula": "9",
        "apartado": "9.2.1",
        "nombre": "Auditoría interna general",
        "contenido_minimo": "Criterios, alcance, independencia, competencia, ejecución y seguimiento de auditorías.",
        "evidencia_sugerida": "Criterios de auditoría, perfiles de auditores, papeles de trabajo y seguimiento.",
        "criticidad": 3,
    },
)


def _build_iso45001_v2_controls() -> tuple[dict, ...]:
    documents_by_code = {
        document["codigo"]: document
        for document in ISO45001_VERSION["documentos_obligatorios"]
    }
    controls: list[dict] = []

    for document in ISO45001_VERSION["documentos_obligatorios"]:
        code = document["codigo"]
        # D-13 corresponde exclusivamente a las generalidades de 7.5.1.
        # La hoja fuente lo agrupaba bajo 7.5, pero v2 deja el alcance
        # explícito para no absorber creación, actualización ni control.
        control_section = "7.5.1" if code == "D-13" else document["apartado"]
        controls.append(
            {
                "codigo": code,
                "tipo": "documento_normativo",
                "clausula": control_section.split(".", 1)[0],
                "apartado": control_section,
                "clasificacion": document["clasificacion"],
                "nombre": document["nombre"],
                "descripcion": "Control normativo de información documentada de ISO 45001.",
                "contenido_minimo": document["contenido_minimo"],
                "evidencia_sugerida": (
                    "Documento o registro vigente que cubra los puntos mínimos y permita "
                    "trazarlo con los reactivos relacionados."
                ),
                "criticidad": document["criticidad"],
                "orden": document["orden"],
                "codigo_documento": code,
                "reactivos": list(ISO45001_V2_CONTROL_REACTIVE_CODES[code]),
                "puntos": [
                    {"orden": index, "texto": text}
                    for index, text in enumerate(ISO45001_V2_CONTROL_POINTS[code], start=1)
                ],
            }
        )

    for offset, spec in enumerate(ISO45001_V2_COMPLEMENTARY_CONTROL_SPECS, start=1):
        code = spec["codigo"]
        controls.append(
            {
                **spec,
                "tipo": "grupo_complementario",
                "clasificacion": "Complementaria",
                "descripcion": "Grupo complementario de evidencia para valorar cobertura operativa.",
                "orden": ISO45001_NORMATIVE_CONTROL_COUNT + offset,
                "codigo_documento": None,
                "reactivos": list(ISO45001_V2_CONTROL_REACTIVE_CODES[code]),
                "puntos": [
                    {"orden": index, "texto": text}
                    for index, text in enumerate(ISO45001_V2_CONTROL_POINTS[code], start=1)
                ],
            }
        )

    if set(documents_by_code) != {f"D-{index:02d}" for index in range(1, 32)}:
        raise RuntimeError("El catálogo documental v2 debe conservar los 31 documentos normativos.")
    return tuple(controls)


ISO45001_V2_CONTROL_EVIDENCE = _build_iso45001_v2_controls()


def _build_iso45001_v2_version() -> dict:
    """Duplicate v1 content while replacing inferred document coverage with v2 matrix."""

    version = deepcopy(ISO45001_VERSION)
    version["slug"] = ISO45001_V2_CATALOG_SLUG
    version["nombre"] = (
        "Diagnóstico de implementación ISO 45001:2018 + Amd. 1:2024 "
        "— cobertura documental por control"
    )
    version["descripcion"] = (
        "Versión inmutable del diagnóstico ISO 45001 que evalúa la cobertura de información "
        "documentada mediante controles reutilizables, sin exigir un adjunto por reactivo."
    )
    version["tipo_cobertura_documental"] = "por_control"
    version["controles_evidencia"] = deepcopy(ISO45001_V2_CONTROL_EVIDENCE)

    documents_by_reactive: dict[str, list[str]] = {}
    for control in ISO45001_V2_CONTROL_EVIDENCE:
        if control["tipo"] != "documento_normativo":
            continue
        for reactive_code in control["reactivos"]:
            documents_by_reactive.setdefault(reactive_code, []).append(control["codigo"])

    for document in version["documentos_obligatorios"]:
        document["reactivos"] = [
            reactive_code
            for reactive_code in ISO45001_V2_CONTROL_REACTIVE_CODES[document["codigo"]]
        ]

    for clause in version["clausulas"]:
        for section in clause["apartados"]:
            for reactive in section["reactivos"]:
                explicit_documents = documents_by_reactive.get(reactive["codigo"], [])
                reactive["documentos_requeridos"] = list(explicit_documents)
                # Conserva el dato de trazabilidad para la interfaz, pero v2 no usa
                # este indicador como condición de adjunto individual.
                reactive["requiere_documento"] = bool(explicit_documents)

    return version


def _validate_v2_catalog(version: dict) -> None:
    reactives = [
        reactive
        for clause in version["clausulas"]
        for section in clause["apartados"]
        for reactive in section["reactivos"]
    ]
    controls = version["controles_evidencia"]
    controls_by_code = {control["codigo"]: control for control in controls}

    if version["slug"] != ISO45001_V2_CATALOG_SLUG:
        raise RuntimeError("La versión de cobertura documental ISO 45001 debe usar su slug v2.")
    if len(reactives) != ISO45001_REACTIVE_COUNT:
        raise RuntimeError("El catálogo ISO 45001 v2 debe duplicar los 308 reactivos.")
    if len(version["documentos_obligatorios"]) != ISO45001_DOCUMENT_COUNT:
        raise RuntimeError("El catálogo ISO 45001 v2 debe duplicar los 31 documentos normativos.")
    if len(controls) != ISO45001_CONTROL_EVIDENCE_COUNT:
        raise RuntimeError("La cobertura documental v2 debe tener 37 controles.")
    if [control["codigo"] for control in controls[:31]] != [
        f"D-{index:02d}" for index in range(1, 32)
    ]:
        raise RuntimeError("Los controles normativos v2 deben conservar D-01 a D-31.")
    if [control["codigo"] for control in controls[31:]] != [
        f"G-{index:02d}" for index in range(1, 7)
    ]:
        raise RuntimeError("La cobertura v2 debe incluir G-01 a G-06.")
    if (
        controls_by_code["D-13"]["apartado"] != "7.5.1"
        or controls_by_code["D-13"]["reactivos"] != list(_reactive_codes((166, 170)))
    ):
        raise RuntimeError("D-13 debe cubrir únicamente los reactivos del apartado 7.5.1.")
    expected_overlaps = {
        "D-23": _reactive_codes((241, 247), (249, 250)),
        "D-24": _reactive_codes((248, 248), (250, 250)),
        "D-26": _reactive_codes((263, 267), (270, 270)),
        "D-27": _reactive_codes((268, 270)),
        "D-29": _reactive_codes((287, 288), (290, 292), (298, 298)),
        "D-30": _reactive_codes((289, 289), (293, 298)),
    }
    for code, expected in expected_overlaps.items():
        if tuple(controls_by_code[code]["reactivos"]) != expected:
            raise RuntimeError(f"El mapeo explícito de {code} no coincide con la matriz v2.")
    if any(not control["puntos"] for control in controls):
        raise RuntimeError("Todo control documental v2 debe tener al menos un punto mínimo.")


ISO45001_V2_VERSION = _build_iso45001_v2_version()
_validate_v2_catalog(ISO45001_V2_VERSION)
