def option_map(zero: str, one: str, two: str, three: str) -> dict[str, str]:
    return {"0": zero, "1": one, "2": two, "3": three}


OFFICIAL_QUESTIONNAIRE = {
    "nombre": "Diagnóstico Integral Municipal 2026",
    "descripcion": (
        "Cuestionario oficial para evaluar la madurez administrativa municipal "
        "en ocho ejes estratégicos con 80 reactivos."
    ),
    "ejes": [
        {
            "clave": "E1",
            "orden": 1,
            "nombre": "Austeridad y eficiencia administrativa",
            "descripcion": (
                "Evalúa lineamientos, controles e indicadores para racionalidad "
                "del gasto corriente y uso eficiente de recursos."
            ),
            "ponderacion": 0.15,
            "reactivos": [
                {"codigo": "1.1", "pregunta": "¿La dependencia cuenta con lineamientos internos o criterios operativos para regular el uso de consumibles, materiales y recursos de oficina?", "opciones": option_map("No existen lineamientos.", "Existen criterios informales pero no documentados.", "Hay políticas documentadas pero sin seguimiento riguroso.", "Se aplican lineamientos formales y se auditan periódicamente.")},
                {"codigo": "1.2", "pregunta": "¿Se realizan controles periódicos para identificar consumos excesivos o no justificados de papelería, combustible, energía, agua o insumos generales?", "opciones": option_map("No se realizan controles.", "Controles ocasionales sin registro.", "Controles semestrales con registros parciales.", "Controles sistemáticos con reportes y acciones correctivas.")},
                {"codigo": "1.3", "pregunta": "¿La dependencia conoce y aplica criterios de racionalidad presupuestal en adquisiciones menores, contratación de servicios y uso de recursos materiales?", "opciones": option_map("No se conocen criterios.", "Criterios generales sin aplicación.", "Criterios aplicados en algunas adquisiciones.", "Criterios aplicados en todos los procesos de adquisición.")},
                {"codigo": "1.4", "pregunta": "¿Existen mecanismos para detectar duplicidades de gasto, compras innecesarias o erogaciones que no generan valor público?", "opciones": option_map("No existen mecanismos.", "Revisión esporádica por parte del personal de compras.", "Mecanismos parciales para algunas áreas.", "Procesos formales de detección y cancelación de gastos innecesarios.")},
                {"codigo": "1.5", "pregunta": "¿Se evalúa periódicamente si los recursos asignados al gasto corriente son suficientes, insuficientes o están sobredimensionados?", "opciones": option_map("No se evalúa.", "Evaluaciones informales.", "Evaluaciones con informes de área pero sin ajuste presupuestal.", "Evaluaciones periódicas que derivan en ajustes presupuestarios.")},
                {"codigo": "1.6", "pregunta": "¿La dependencia documenta medidas de ahorro implementadas durante el ejercicio fiscal?", "opciones": option_map("No se documenta.", "Se documentan algunas acciones de ahorro.", "Se documentan todas las medidas pero sin evaluación de impacto.", "Se documentan y se analiza el impacto de cada medida.")},
                {"codigo": "1.7", "pregunta": "¿Se cuenta con indicadores o reportes que permitan medir eficiencia en el gasto corriente?", "opciones": option_map("No existen indicadores.", "Hay indicadores pero no se actualizan regularmente.", "Indicadores actualizados parcialmente.", "Indicadores actualizados y usados para la toma de decisiones.")},
                {"codigo": "1.8", "pregunta": "¿Las personas servidoras públicas responsables de administrar recursos conocen las disposiciones municipales en materia de austeridad y eficiencia?", "opciones": option_map("Desconocen las disposiciones.", "Conocen lineamientos de manera general.", "Conocen y aplican disposiciones en su área.", "Conocen, aplican y promueven la austeridad en toda la dependencia.")},
                {"codigo": "1.9", "pregunta": "¿La dependencia ha identificado áreas de oportunidad para reducir costos sin afectar la continuidad del servicio público?", "opciones": option_map("No se han identificado.", "Se han identificado de manera informal.", "Se identifican y se proponen medidas de ahorro puntuales.", "Se identifican, priorizan e implementan medidas de ahorro sostenibles.")},
                {"codigo": "1.10", "pregunta": "¿Existen barreras normativas, operativas o culturales que dificulten la implementación de medidas de austeridad y eficiencia en la dependencia?", "opciones": option_map("Se desconocen barreras.", "Se reconocen barreras pero no se hace nada.", "Se conocen barreras y se gestionan parcialmente.", "Se conoce y se trabaja activamente para eliminar barreras.")},
            ],
        },
        {
            "clave": "E2",
            "orden": 2,
            "nombre": "Gobierno electrónico y modernización administrativa",
            "descripcion": (
                "Mide digitalización, automatización y modernización de procesos, "
                "así como la reducción de trámites en papel."
            ),
            "ponderacion": 0.20,
            "reactivos": [
                {"codigo": "2.1", "pregunta": "¿Qué porcentaje aproximado de los trámites, solicitudes, oficios o gestiones internas de la dependencia se realizan actualmente de forma digital?", "opciones": option_map("Menos del 10%.", "10-30%.", "30-70%.", "Más del 70%.")},
                {"codigo": "2.2", "pregunta": "¿La dependencia utiliza sistemas informáticos institucionales para el registro, seguimiento y control de sus procesos administrativos?", "opciones": option_map("No utiliza sistemas.", "Utiliza sistemas en algunas áreas.", "Utiliza sistemas en la mayoría de áreas.", "Utiliza sistemas integrados en todas las áreas.")},
                {"codigo": "2.3", "pregunta": "¿Existen procedimientos que aún dependan totalmente del uso de papel, firmas autógrafas o archivo físico?", "opciones": option_map("Existen múltiples procedimientos manuales.", "Algunos procesos siguen siendo manuales.", "Solo procedimientos excepcionales dependen del papel.", "Se ha eliminado totalmente el uso de papel.")},
                {"codigo": "2.4", "pregunta": "¿La dependencia ha identificado procesos susceptibles de digitalización o simplificación administrativa?", "opciones": option_map("No se han identificado.", "Identificación parcial.", "Identificación completa pero sin plan.", "Identificación y plan de digitalización.")},
                {"codigo": "2.5", "pregunta": "¿Se cuenta con diagnóstico de necesidades tecnológicas para avanzar hacia un esquema de gobierno electrónico?", "opciones": option_map("No se cuenta con diagnóstico.", "Diagnóstico básico.", "Diagnóstico detallado para algunas áreas.", "Diagnóstico integral y actualizado.")},
                {"codigo": "2.6", "pregunta": "¿Las personas usuarias internas tienen acceso suficiente a equipo, conectividad y herramientas digitales para operar sus funciones?", "opciones": option_map("Acceso insuficiente.", "Acceso parcial pero limitado.", "Acceso suficiente para la mayoría del personal.", "Acceso completo y de calidad para todo el personal.")},
                {"codigo": "2.7", "pregunta": "¿La dependencia dispone de controles para evitar duplicidad de captura de información entre formatos físicos y electrónicos?", "opciones": option_map("No hay controles.", "Controles informales.", "Controles parciales.", "Controles formales y mecanismos de interoperabilidad.")},
                {"codigo": "2.8", "pregunta": "¿Existen tiempos excesivos de respuesta causados por procesos manuales o por circulación física de documentos?", "opciones": option_map("Los tiempos de respuesta son excesivos.", "Los tiempos se redujeron parcialmente.", "Los tiempos son moderados.", "No hay retrasos atribuibles a procesos manuales.")},
                {"codigo": "2.9", "pregunta": "¿La dependencia cuenta con evidencia de proyectos previos o actuales de modernización administrativa?", "opciones": option_map("No hay evidencia.", "Existen iniciativas aisladas.", "Proyectos con resultados limitados.", "Proyectos de modernización con resultados consolidados.")},
                {"codigo": "2.10", "pregunta": "¿Qué limitantes técnicas, presupuestales, normativas o de capacitación dificultan la eliminación progresiva del uso de papel en la dependencia?", "opciones": option_map("No se han identificado limitantes.", "Se conocen limitantes pero no se gestionan.", "Se gestionan parcialmente.", "Se han superado las limitantes y se mantienen acciones de mejora continua.")},
            ],
        },
        {
            "clave": "E3",
            "orden": 3,
            "nombre": "Mejora continua",
            "descripcion": (
                "Analiza la capacidad institucional para revisar procesos y "
                "realizar ajustes que incrementen la eficiencia."
            ),
            "ponderacion": 0.15,
            "reactivos": [
                {"codigo": "3.1", "pregunta": "¿La dependencia tiene identificados y documentados sus procesos sustantivos, adjetivos y de apoyo?", "opciones": option_map("No se identifican.", "Documentación parcial.", "Documentación completa pero desactualizada.", "Documentación completa y actualizada.")},
                {"codigo": "3.2", "pregunta": "¿Se revisan periódicamente los procedimientos administrativos para detectar ineficiencias, retrasos o actividades sin valor agregado?", "opciones": option_map("Nunca.", "Revisiones puntuales.", "Revisiones periódicas pero sin seguimiento.", "Revisiones periódicas con acciones correctivas.")},
                {"codigo": "3.3", "pregunta": "¿La dependencia cuenta con mecanismos formales para proponer mejoras en procesos, formatos, flujos o controles?", "opciones": option_map("No existen.", "Mecanismos informales.", "Mecanismos formales pero poco utilizados.", "Mecanismos formales y utilizados regularmente.")},
                {"codigo": "3.4", "pregunta": "¿Existen indicadores de desempeño que permitan evaluar la eficiencia de los procesos administrativos?", "opciones": option_map("No existen.", "Existen indicadores básicos.", "Indicadores estructurados pero con poca medición.", "Indicadores estructurados y medición frecuente.")},
                {"codigo": "3.5", "pregunta": "¿Se levantan incidencias, observaciones o hallazgos que sirvan como insumo para la mejora continua?", "opciones": option_map("No se levantan.", "Se levantan de manera informal.", "Se levantan y se registran, pero sin análisis.", "Se levantan, analizan y se genera plan de mejora.")},
                {"codigo": "3.6", "pregunta": "¿La dependencia ha realizado ejercicios de simplificación administrativa, reingeniería o rediseño de procesos en los últimos años?", "opciones": option_map("No se han realizado.", "Iniciativas aisladas.", "Proyectos parciales.", "Proyectos integrales de simplificación.")},
                {"codigo": "3.7", "pregunta": "¿Se involucra al personal operativo en la identificación de problemas y propuestas de mejora?", "opciones": option_map("No se involucra.", "Participación esporádica.", "Participación parcial en talleres.", "Participación activa y sistemática.")},
                {"codigo": "3.8", "pregunta": "¿Las mejoras implementadas se documentan, comunican y evalúan posteriormente para verificar su efectividad?", "opciones": option_map("No se documenta ni comunica.", "Se documenta pero no se evalúa.", "Se documenta y se comunica.", "Se documenta, comunica y evalúa la efectividad.")},
                {"codigo": "3.9", "pregunta": "¿Se presentan cuellos de botella o duplicidad de funciones entre áreas internas de la misma dependencia?", "opciones": option_map("Sí, con frecuencia.", "Ocasionalmente.", "Rara vez.", "No se presentan cuellos de botella.")},
                {"codigo": "3.10", "pregunta": "¿La dependencia considera que su estructura actual permite operar con eficiencia o requiere ajustes organizacionales?", "opciones": option_map("Requiere ajustes urgentes.", "Requiere ajustes moderados.", "Requiere ajustes menores.", "Estructura adecuada y eficiente.")},
            ],
        },
        {
            "clave": "E4",
            "orden": 4,
            "nombre": "Capacitación y profesionalización",
            "descripcion": (
                "Identifica necesidades de capacitación, formación y "
                "profesionalización del personal municipal."
            ),
            "ponderacion": 0.10,
            "reactivos": [
                {"codigo": "4.1", "pregunta": "¿La dependencia cuenta con un diagnóstico de necesidades de capacitación vinculado con sus funciones y procesos?", "opciones": option_map("No existe.", "Se tiene un diagnóstico preliminar.", "Diagnóstico detallado para algunas áreas.", "Diagnóstico integral actualizado.")},
                {"codigo": "4.2", "pregunta": "¿El personal recibe capacitación periódica para mejorar el desempeño de sus responsabilidades?", "opciones": option_map("Nunca.", "Ocasional.", "Capacitación semestral.", "Capacitación continua y planificada.")},
                {"codigo": "4.3", "pregunta": "¿La capacitación impartida guarda relación directa con los problemas operativos y necesidades reales del área?", "opciones": option_map("No guarda relación.", "Relación parcial.", "Relación directa en algunos cursos.", "Relación directa y focalizada.")},
                {"codigo": "4.4", "pregunta": "¿Existen puestos críticos que actualmente se desempeñan sin la formación técnica suficiente?", "opciones": option_map("Muchos puestos.", "Algunos puestos.", "Pocos puestos.", "No existen puestos sin la formación técnica suficiente.")},
                {"codigo": "4.5", "pregunta": "¿La dependencia evalúa el impacto de la capacitación en la mejora del servicio o en la reducción de errores operativos?", "opciones": option_map("No evalúa.", "Evaluación informal.", "Evaluación formal en algunas áreas.", "Evaluación formal sistemática.")},
                {"codigo": "4.6", "pregunta": "¿Se identifican brechas de conocimiento en temas normativos, tecnológicos, administrativos o de atención ciudadana?", "opciones": option_map("No se identifican.", "Identificación parcial.", "Identificación y priorización.", "Identificación, priorización y plan de acción.")},
                {"codigo": "4.7", "pregunta": "¿El personal de nuevo ingreso recibe inducción formal sobre funciones, procedimientos y responsabilidades del puesto?", "opciones": option_map("No recibe inducción.", "Inducción básica informal.", "Inducción formal inicial.", "Inducción formal y seguimiento.")},
                {"codigo": "4.8", "pregunta": "¿La dependencia promueve procesos de profesionalización, certificación o formación especializada?", "opciones": option_map("No promueve.", "Promueve ocasionalmente.", "Promueve para algunas áreas.", "Promueve de manera institucional.")},
                {"codigo": "4.9", "pregunta": "¿Qué obstáculos enfrenta el personal para acceder a programas de capacitación, actualización o desarrollo?", "opciones": option_map("Falta de programas y recursos.", "Falta de recursos.", "Falta de interés.", "No existen obstáculos significativos.")},
                {"codigo": "4.10", "pregunta": "¿La dependencia considera que fortalecer las competencias del personal tendría impacto directo en la eficiencia institucional y en la calidad del servicio público?", "opciones": option_map("No lo considera.", "Lo considera de manera general.", "Lo considera y lo incluye en proyectos de capacitación.", "Lo considera y lo ejecuta activamente.")},
            ],
        },
        {
            "clave": "E5",
            "orden": 5,
            "nombre": "Manuales y perfiles de puesto",
            "descripcion": (
                "Evalúa si la estructura de puestos está claramente definida, "
                "actualizada y alineada con las funciones reales."
            ),
            "ponderacion": 0.10,
            "reactivos": [
                {"codigo": "5.1", "pregunta": "¿La dependencia cuenta con manuales de descripción y perfil de puestos actualizados y formalmente validados?", "opciones": option_map("No cuenta con manuales.", "Manuales desactualizados.", "Manuales actualizados parcialmente.", "Manuales actualizados y validados.")},
                {"codigo": "5.2", "pregunta": "¿Las funciones que desempeña el personal corresponden efectivamente con la descripción formal de su puesto?", "opciones": option_map("No corresponden.", "Corresponden parcialmente.", "Corresponden en la mayoría de los casos.", "Corresponden en todos los casos.")},
                {"codigo": "5.3", "pregunta": "¿Existen puestos con funciones ambiguas, duplicadas o no claramente delimitadas?", "opciones": option_map("Muchos casos.", "Algunos casos.", "Pocos casos.", "No existen.")},
                {"codigo": "5.4", "pregunta": "¿Se han identificado cambios operativos que hagan necesaria la actualización de perfiles de puesto?", "opciones": option_map("No se han identificado.", "Se identifican pero no se actualizan.", "Se identifican y se actualizan parcialmente.", "Se identifican y se actualizan oportunamente.")},
                {"codigo": "5.5", "pregunta": "¿Los perfiles de puesto establecen claramente escolaridad, experiencia, competencias y conocimientos requeridos?", "opciones": option_map("No.", "De manera parcial.", "Claramente en algunos perfiles.", "Claramente en todos los perfiles.")},
                {"codigo": "5.6", "pregunta": "¿Se utiliza el manual de puestos como herramienta para reclutamiento, capacitación, evaluación del desempeño o reestructuración organizacional?", "opciones": option_map("No se utiliza.", "Se utiliza para reclutamiento únicamente.", "Se utiliza para reclutamiento y capacitación.", "Se utiliza en todas las funciones de gestión de talento.")},
                {"codigo": "5.7", "pregunta": "¿Las jefaturas inmediatas conocen y aplican los perfiles de puesto al asignar responsabilidades?", "opciones": option_map("No los conocen.", "Los conocen pero no los aplican.", "Los conocen y aplican parcialmente.", "Los conocen y aplican plenamente.")},
                {"codigo": "5.8", "pregunta": "¿Existen actividades sustantivas que actualmente no estén reflejadas en los manuales de descripción de puestos?", "opciones": option_map("Sí, en su mayoría.", "Sí, en algunos casos.", "Pocas actividades no reflejadas.", "No existen actividades sin reflejar.")},
                {"codigo": "5.9", "pregunta": "¿Se presentan casos donde una persona ocupe formalmente un puesto pero realice funciones distintas por necesidades del servicio?", "opciones": option_map("Es frecuente.", "Ocasionalmente.", "Rara vez.", "No se presentan.")},
                {"codigo": "5.10", "pregunta": "¿La actualización de los manuales contribuiría a mejorar la eficiencia, la claridad jerárquica y la rendición de cuentas en la dependencia?", "opciones": option_map("No.", "Contribuiría poco.", "Contribuiría moderadamente.", "Contribuiría significativamente.")},
            ],
        },
        {
            "clave": "E6",
            "orden": 6,
            "nombre": "Eficiencia energética",
            "descripcion": (
                "Evalúa medidas para reducir consumo eléctrico y optimizar el uso "
                "de equipos e infraestructura."
            ),
            "ponderacion": 0.05,
            "reactivos": [
                {"codigo": "6.1", "pregunta": "¿La dependencia cuenta con medidas específicas para reducir el consumo de energía eléctrica en oficinas e instalaciones?", "opciones": option_map("No cuenta con medidas.", "Medidas aisladas.", "Medidas implantadas en algunas áreas.", "Plan integral de ahorro energético.")},
                {"codigo": "6.2", "pregunta": "¿Se realizan revisiones periódicas sobre el uso de equipos de aire acondicionado, iluminación, cómputo y otros dispositivos de alto consumo?", "opciones": option_map("No se realizan.", "Revisiones ocasionales.", "Revisiones programadas pero sin evaluación de resultados.", "Revisiones programadas y evaluación de resultados.")},
                {"codigo": "6.3", "pregunta": "¿El personal conoce prácticas básicas de ahorro energético dentro de su centro de trabajo?", "opciones": option_map("No las conoce.", "Las conoce parcialmente.", "Las conoce y las aplica en ocasiones.", "Las conoce y las aplica regularmente.")},
                {"codigo": "6.4", "pregunta": "¿Existen instalaciones, equipos o infraestructura obsoleta que generen consumo excesivo de energía?", "opciones": option_map("Sí, en gran medida.", "Sí, pero en menor proporción.", "Equipos obsoletos en algunas áreas.", "No existen equipos obsoletos.")},
                {"codigo": "6.5", "pregunta": "¿La dependencia cuenta con información histórica sobre su consumo energético para identificar tendencias o áreas críticas?", "opciones": option_map("No existe información.", "Información incompleta.", "Información histórica limitada.", "Información completa y análisis de tendencias.")},
                {"codigo": "6.6", "pregunta": "¿Se han implementado acciones como sustitución de luminarias, control de horarios de equipos o mantenimiento preventivo con enfoque de eficiencia?", "opciones": option_map("No se han implementado.", "Medidas aisladas.", "Medidas parciales.", "Medidas integrales y sostenidas.")},
                {"codigo": "6.7", "pregunta": "¿Existen responsables designados para supervisar buenas prácticas de uso de energía?", "opciones": option_map("No.", "Responsables informales.", "Responsables formales pero sin seguimiento.", "Responsables formales con seguimiento y reportes.")},
                {"codigo": "6.8", "pregunta": "¿La dependencia ha recibido lineamientos institucionales en materia de ahorro y eficiencia energética?", "opciones": option_map("No ha recibido.", "Ha recibido algunos lineamientos sin aplicación.", "Ha recibido lineamientos y los aplica parcialmente.", "Ha recibido lineamientos y los aplica plenamente.")},
                {"codigo": "6.9", "pregunta": "¿Qué áreas físicas o procesos presentan mayor potencial de ahorro energético?", "opciones": option_map("No se identifican áreas.", "Se identifican áreas sin plan de acción.", "Se identifican áreas y se propone un plan de acción parcial.", "Se identifican áreas y se desarrolla un plan de acción integral.")},
                {"codigo": "6.10", "pregunta": "¿La dependencia considera viable integrar metas o indicadores de eficiencia energética en su operación cotidiana?", "opciones": option_map("No lo considera viable.", "Lo considera de manera general.", "Lo considera y ha definido metas parciales.", "Lo considera y ha definido metas e indicadores claros.")},
            ],
        },
        {
            "clave": "E7",
            "orden": 7,
            "nombre": "Firma electrónica avanzada",
            "descripcion": (
                "Determina la preparación institucional para adoptar mecanismos "
                "de firma electrónica en gestión interna y atención ciudadana."
            ),
            "ponderacion": 0.10,
            "reactivos": [
                {"codigo": "7.1", "pregunta": "¿La dependencia conoce el marco normativo y los lineamientos aplicables al uso de la Firma Electrónica Avanzada en la administración municipal?", "opciones": option_map("No conoce.", "Conoce superficialmente.", "Conoce y aplica en algunos procesos.", "Conoce y aplica de forma generalizada.")},
                {"codigo": "7.2", "pregunta": "¿Existen procesos internos que podrían resolverse de forma más eficiente mediante el uso de firma electrónica?", "opciones": option_map("No se identifican.", "Se identifican algunos procesos.", "Se identifican y se planifican pilotos.", "Se identifican y se implementan proyectos de firma electrónica.")},
                {"codigo": "7.3", "pregunta": "¿El personal directivo y operativo está preparado para utilizar herramientas de validación, firma y resguardo digital de documentos?", "opciones": option_map("No está preparado.", "Está parcialmente preparado.", "Está preparado en algunas áreas.", "Está completamente preparado.")},
                {"codigo": "7.4", "pregunta": "¿La dependencia cuenta con infraestructura tecnológica suficiente para adoptar esquemas de firma electrónica?", "opciones": option_map("No cuenta con la infraestructura.", "Cuenta parcialmente.", "Cuenta con infraestructura en proceso de fortalecimiento.", "Cuenta con infraestructura suficiente.")},
                {"codigo": "7.5", "pregunta": "¿Existen procedimientos internos que exigen presencia física o firma autógrafa sin que ello sea indispensable?", "opciones": option_map("Sí, en la mayoría de los procesos.", "Sí, en algunos procesos.", "Solo en procesos puntuales.", "No existen procedimientos que exijan presencia física.")},
                {"codigo": "7.6", "pregunta": "¿La dependencia ha identificado riesgos jurídicos, operativos o de seguridad asociados a la transición hacia firma electrónica?", "opciones": option_map("No ha identificado riesgos.", "Ha identificado riesgos pero no los ha evaluado.", "Ha identificado y evaluado riesgos parcialmente.", "Ha identificado, evaluado y mitigado riesgos.")},
                {"codigo": "7.7", "pregunta": "¿Se cuenta con control documental que garantice autenticidad, integridad y trazabilidad de documentos digitales?", "opciones": option_map("No se cuenta con controles.", "Controles básicos.", "Controles completos pero poco utilizados.", "Controles completos y aplicados.")},
                {"codigo": "7.8", "pregunta": "¿El uso de firma electrónica podría reducir tiempos de respuesta en trámites internos o servicios a particulares?", "opciones": option_map("No sería útil.", "Sería útil en algunas áreas.", "Sería útil en varias áreas.", "Sería altamente útil y se están planificando proyectos.")},
                {"codigo": "7.9", "pregunta": "¿Qué cargos o áreas serían prioritarios para iniciar la implementación de firma electrónica avanzada?", "opciones": option_map("No se han definido áreas prioritarias.", "Áreas definidas de manera informal.", "Áreas prioritarias definidas y plan piloto.", "Áreas prioritarias definidas y proyectos en ejecución.")},
                {"codigo": "7.10", "pregunta": "¿La dependencia requiere lineamientos, capacitación o soporte técnico adicional para adoptar este mecanismo de manera efectiva?", "opciones": option_map("No requiere soporte.", "Requiere lineamientos básicos.", "Requiere lineamientos y capacitación parcial.", "Requiere lineamientos, capacitación y soporte integral.")},
            ],
        },
        {
            "clave": "E8",
            "orden": 8,
            "nombre": "Gestión tecnológica y datos",
            "descripcion": (
                "Evalúa infraestructura tecnológica, seguridad informática, "
                "gestión de datos e innovación."
            ),
            "ponderacion": 0.15,
            "reactivos": [
                {"codigo": "8.1", "pregunta": "¿La dependencia cuenta con inventario actualizado de equipos, sistemas, licencias, redes y herramientas tecnológicas utilizadas en su operación?", "opciones": option_map("No cuenta con inventario.", "Inventario desactualizado.", "Inventario actualizado parcialmente.", "Inventario actualizado completo.")},
                {"codigo": "8.2", "pregunta": "¿Los sistemas informáticos actuales responden de manera adecuada a las necesidades funcionales del área?", "opciones": option_map("No responden.", "Responden parcialmente.", "Responden pero requieren mejoras.", "Responden adecuadamente.")},
                {"codigo": "8.3", "pregunta": "¿Existen procesos críticos que aún se operan en hojas de cálculo aisladas, archivos sueltos o mecanismos no integrados?", "opciones": option_map("Todos los procesos críticos.", "Algunos procesos.", "Pocos procesos.", "Ningún proceso.")},
                {"codigo": "8.4", "pregunta": "¿La dependencia ha experimentado fallas frecuentes de conectividad, hardware, software o pérdida de información?", "opciones": option_map("Sí, con frecuencia.", "Ocasionalmente.", "Rara vez.", "No se han experimentado fallas.")},
                {"codigo": "8.5", "pregunta": "¿Se aplican medidas de seguridad informática como control de accesos, respaldos, contraseñas seguras y protección contra malware?", "opciones": option_map("No se aplican.", "Se aplican parcialmente.", "Se aplican en la mayoría de las áreas.", "Se aplican completamente.")},
                {"codigo": "8.6", "pregunta": "¿El personal conoce protocolos básicos de ciberseguridad, manejo de información y prevención de incidentes digitales?", "opciones": option_map("No los conoce.", "Los conoce parcialmente.", "Los conoce pero no los aplica siempre.", "Los conoce y los aplica.")},
                {"codigo": "8.7", "pregunta": "¿La dependencia cuenta con datos organizados, accesibles y confiables para apoyar la toma de decisiones?", "opciones": option_map("No.", "Datos desordenados.", "Datos parcialmente organizados.", "Datos organizados y con calidad.")},
                {"codigo": "8.8", "pregunta": "¿Existen duplicidades, inconsistencias o falta de interoperabilidad entre los sistemas o bases de datos que utiliza la dependencia?", "opciones": option_map("Muchas duplicidades.", "Algunas duplicidades.", "Pocas duplicidades.", "No existen duplicidades.")},
                {"codigo": "8.9", "pregunta": "¿Se brinda soporte técnico oportuno y suficiente para resolver incidencias que afectan la operación diaria?", "opciones": option_map("No se brinda soporte.", "Soporte limitado.", "Soporte moderado.", "Soporte oportuno y suficiente.")},
                {"codigo": "8.10", "pregunta": "¿La dependencia ha identificado proyectos de innovación o transformación digital que puedan mejorar sustancialmente sus servicios, procesos o capacidad de gestión?", "opciones": option_map("No se han identificado.", "Identificación parcial.", "Identificación con proyectos piloto.", "Identificación y ejecución de proyectos de innovación.")},
            ],
        },
    ],
}


RECOMMENDATION_LIBRARY = {
    "Austeridad y eficiencia administrativa": [
        "Formalizar lineamientos de austeridad y establecer auditorías periódicas de gasto corriente.",
        "Crear indicadores de consumo y tableros de seguimiento por tipo de recurso.",
        "Priorizar medidas de ahorro con impacto presupuestal medible.",
    ],
    "Gobierno electrónico y modernización administrativa": [
        "Levantar un portafolio de procesos candidatos a digitalización con metas trimestrales.",
        "Eliminar capturas duplicadas y homologar expedientes digitales.",
        "Fortalecer conectividad, herramientas y capacitación del personal operativo.",
    ],
    "Mejora continua": [
        "Documentar procesos críticos y establecer revisiones periódicas con responsables.",
        "Crear un mecanismo formal para registrar incidencias y planes de mejora.",
        "Involucrar al personal operativo en rediseño y simplificación administrativa.",
    ],
    "Capacitación y profesionalización": [
        "Construir un diagnóstico anual de necesidades de capacitación por área.",
        "Vincular capacitación con brechas reales y evaluar su impacto operativo.",
        "Institucionalizar inducción y rutas de profesionalización para puestos críticos.",
    ],
    "Manuales y perfiles de puesto": [
        "Actualizar manuales y perfiles con funciones reales y competencias requeridas.",
        "Usar perfiles de puesto para reclutamiento, capacitación y evaluación del desempeño.",
        "Corregir ambigüedades y duplicidades de funciones entre áreas.",
    ],
    "Eficiencia energética": [
        "Definir un plan de ahorro energético con metas e indicadores por instalación.",
        "Asignar responsables y calendarizar revisiones de equipos de alto consumo.",
        "Priorizar reemplazos de infraestructura obsoleta con mayor retorno operativo.",
    ],
    "Firma electrónica avanzada": [
        "Definir pilotos de firma electrónica para procesos de alto volumen documental.",
        "Fortalecer lineamientos, control documental y gestión de riesgos jurídicos.",
        "Capacitar a áreas prioritarias y robustecer infraestructura de soporte.",
    ],
    "Gestión tecnológica y datos": [
        "Actualizar inventario tecnológico y plan anual de mantenimiento.",
        "Reducir sistemas aislados y mejorar interoperabilidad y calidad de datos.",
        "Reforzar ciberseguridad, respaldos y soporte a incidencias operativas.",
    ],
}
