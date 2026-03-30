WELLBEING_REACTIVE_INDICATOR = "indicador"
WELLBEING_REACTIVE_PROFILE = "perfil"


def q(dimension: str, texto: str, opciones: list[str], *, tipo_reactivo: str = WELLBEING_REACTIVE_INDICATOR) -> dict:
    return {
        "dimension": dimension,
        "texto": texto,
        "opciones": opciones,
        "tipo_reactivo": tipo_reactivo,
    }


DEFAULT_WELLBEING_QUESTIONS = [
    q("Bienestar Psicológico", "¿Con qué frecuencia se siente abrumado por sus responsabilidades laborales?", ["Nunca", "A veces", "Frecuentemente", "Casi siempre"]),
    q("Bienestar Psicológico", "¿Experimenta cambios de humor repentinos o irritabilidad?", ["Nunca", "A veces", "Frecuentemente", "Casi siempre"]),
    q("Bienestar Psicológico", "¿Siente que su trabajo interfiere con su paz mental?", ["En absoluto", "Poco", "Bastante", "Totalmente"]),
    q("Bienestar Psicológico", "¿Tiene dificultades para dormir debido a preocupaciones laborales?", ["Nunca", "A veces", "Frecuentemente", "Casi siempre"]),
    q("Bienestar Psicológico", "¿Se siente valorado por la comunidad a la que sirve?", ["Siempre", "Generalmente", "Rara vez", "Nunca"]),
    q("Bienestar Psicológico", "¿Experimenta síntomas físicos de ansiedad durante su jornada?", ["Nunca", "Ocasionalmente", "Frecuentemente", "Constantemente"]),
    q("Bienestar Psicológico", "¿Siente que tiene un propósito claro en su profesión?", ["Totalmente", "En gran medida", "A medias", "Muy poco"]),
    q("Situación Socioeconómica", "¿Sus ingresos le permiten cubrir necesidades básicas sin endeudarse?", ["Totalmente", "Cubro lo básico", "Apenas suficiente", "Insuficiente"]),
    q("Situación Socioeconómica", "¿Qué porcentaje de su ingreso destina al pago de deudas?", ["Menos del 10%", "10% a 30%", "31% a 50%", "Más del 50%"]),
    q("Situación Socioeconómica", "¿Cuál es su situación actual de vivienda?", ["Propia pagada", "Pagando cómodamente", "Rentando", "Pagando con dificultad"]),
    q("Situación Socioeconómica", "¿Tiene dependientes económicos con necesidades médicas especiales?", ["No tengo", "Sí, cubierto", "Sí, carga moderada", "Sí, presión fuerte"]),
    q("Situación Socioeconómica", "¿Considera justo su salario en relación con los riesgos que asume?", ["Totalmente justo", "Aceptable", "Poco justo", "Nada justo"]),
    q("Situación Socioeconómica", "¿Tiene un trabajo adicional para solventar gastos?", ["No", "No, aunque es justo", "Sí, ocasional", "Sí, constante"]),
    q("Salud Física", "¿Cuántos días a la semana realiza actividad física al menos 30 minutos?", ["3 o más", "1 o 2", "Ocasionalmente", "Nunca"]),
    q("Salud Física", "¿Cómo calificaría su alimentación durante su jornada?", ["Saludable", "Aceptable", "Irregular", "Muy mala"]),
    q("Salud Física", "¿Padece alguna enfermedad crónica que afecte su bienestar?", ["Ninguna", "Sí, controlada", "Sí, da problemas", "Sí, afecta gravemente"]),
    q("Salud Física", "¿Con qué frecuencia acude a revisiones médicas preventivas?", ["Anualmente", "Solo si me siento mal", "Rara vez", "Nunca"]),
    q("Salud Física", "¿Siente dolores físicos recurrentes asociados a su labor?", ["Nunca", "Ocasionalmente", "Frecuentemente", "Constantemente"]),
    q("Demandas Laborales", "¿Los turnos le permiten descansar adecuadamente?", ["Siempre", "Casi siempre", "Rara vez", "Nunca"]),
    q("Demandas Laborales", "¿Con qué frecuencia se extiende su turno sin previo aviso?", ["Nunca", "Rara vez", "Frecuentemente", "Constantemente"]),
    q("Demandas Laborales", "¿Qué nivel de riesgo físico asume en sus actividades?", ["Bajo", "Moderado", "Alto", "Extremo"]),
    q("Demandas Laborales", "¿Con qué frecuencia lidia con situaciones de violencia o trauma?", ["Casi nunca", "A veces", "Frecuentemente", "A diario"]),
    q("Demandas Laborales", "¿La carga de trabajo está distribuida equitativamente?", ["Totalmente", "Generalmente", "Poco", "Desproporcionada"]),
    q("Demandas Laborales", "¿Se siente presionado para cumplir cuotas o metas operativas?", ["Nunca", "Rara vez", "Frecuentemente", "Constantemente"]),
    q("Recursos Organizacionales", "¿Su equipo de trabajo se encuentra en buen estado?", ["Excelente", "Requiere mantenimiento", "Faltan insumos", "Deficiente"]),
    q("Recursos Organizacionales", "¿Recibe capacitación constante y útil?", ["Constante", "Mejorable", "Desactualizada", "No recibo"]),
    q("Recursos Organizacionales", "¿Las instalaciones en las que opera son adecuadas?", ["Excelentes", "Aceptables", "Deficientes", "Pésimas"]),
    q("Recursos Organizacionales", "¿Siente el respaldo de sus mandos ante un incidente?", ["Siempre", "Casi siempre", "Rara vez", "Me dejarían solo"]),
    q("Recursos Organizacionales", "¿Existen canales de comunicación efectivos con sus mandos?", ["Abiertos", "Lentos", "Difíciles", "No existen"]),
    q("Recursos Organizacionales", "¿El proceso para permisos o vacaciones es ágil?", ["Rápido", "Burocrático", "Difícil", "Por favoritismo"]),
    q("Apoyo Familiar", "¿Cuenta con apoyo emocional de su familia respecto a su labor?", ["Totalmente", "Generalmente", "Tienen reservas", "No apoyan"]),
    q("Apoyo Familiar", "¿Su trabajo le impide asistir a eventos familiares importantes?", ["Casi nunca", "A veces", "Frecuentemente", "Casi siempre"]),
    q("Apoyo Familiar", "¿Sus horarios le permiten convivir con calidad con su familia?", ["Buen equilibrio", "Es difícil", "Poco tiempo", "No lo permite"]),
    q("Apoyo Familiar", "¿Su familia vive con temor constante por su labor?", ["Lo asimilan", "Normal", "Mucha preocupación", "Temor constante"]),
    q("Apoyo Familiar", "¿Tiene con quién hablar abiertamente sobre experiencias difíciles?", ["Familia o amigos", "Compañeros", "Rara vez", "Me lo guardo"]),
    q("Situación Socioeconómica", "¿Cuál es su estado civil actual?", ["Soltero(a)", "Casado(a) o unión libre", "Separado(a) o divorciado(a)", "Viudo(a)"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Cuántos dependientes económicos tiene actualmente?", ["Ninguno", "1", "2 a 3", "4 o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Cuántos de sus dependientes económicos son menores de edad?", ["Ninguno", "1", "2", "3 o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Cuántos de sus dependientes económicos son personas adultas mayores?", ["Ninguno", "1", "2", "3 o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Es usted el principal sostén económico de su hogar?", ["Sí, totalmente", "Sí, compartido con otra persona", "Aporto, pero no soy principal", "No soy sostén económico principal"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Cuántas personas aportan ingreso económico en su hogar?", ["1 persona", "2 personas", "3 personas", "4 o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Cuál describe mejor la composición actual de su hogar?", ["Vive solo(a)", "Pareja sin hijos", "Pareja con hijos o hijas", "Hogar extendido o multigeneracional"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Tiene algún dependiente económico con discapacidad, enfermedad crónica o necesidad permanente de cuidados?", ["No", "Sí, uno con apoyo controlado", "Sí, uno con alta demanda de cuidado", "Sí, dos o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Tiene dependientes económicos que actualmente estudian y dependen de su ingreso?", ["Ninguno", "1", "2", "3 o más"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
    q("Situación Socioeconómica", "¿Qué nivel de presión económica representan sus dependientes para el gasto mensual del hogar?", ["Baja", "Moderada", "Alta", "Muy alta"], tipo_reactivo=WELLBEING_REACTIVE_PROFILE),
]

DEFAULT_WELLBEING_STRATA = ["E1", "E2", "E3", "E4", "E5"]
