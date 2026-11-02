"""
Catálogo maestro de materias.

A partir de este cambio, TODO el pipeline (proyección + solver) usa el
código de materia (MA####) como identificador único — no el nombre en
texto libre. Esto elimina de raíz los problemas de tildes, mayúsculas,
o variantes de escritura del mismo nombre ("PENSAMENTO CRÍTICO..." vs
"Pensamiento Crítico...", etc.): dos materias son la misma si y solo si
tienen el mismo código, punto.

Este diccionario solo se usa para RESOLVER el nombre bonito que se
muestra en pantalla/Excel a partir del código. La lógica de negocio
(semestres, prerrequisitos, tope de 20, franja 18-20) usa el código
directamente — ver SEMESTRES/PRERREQUISITOS en proyeccion.py y
MATERIAS_MAX20/MATERIAS_FRANJA_LIBRE en scheduler.py.

Nota sobre los dos bloques de códigos: el bloque MA0100-MA0145 (+MA0001
Pre Cálculo, compartido) es el PÉNSUM VIGENTE — coincide con la
estructura de semestres/prerrequisitos que ya tenías armada. El bloque
MA0024-MA0063 es un plan anterior/paralelo: se reconoce aquí para que
el nombre no salga en blanco si aparece en un dataset viejo, pero NO
tiene semestre ni prerrequisitos asignados en SEMESTRES/PRERREQUISITOS
(si necesitas que ese plan también proyecte con prerrequisitos, hay que
agregarlo aparte — avísame y lo armamos).
"""

CATALOGO_MATERIAS: dict[str, str] = {
    # --- Plan anterior (histórico, MA0024-MA0063) ---
    "MA0024": "Cálculo 1",
    "MA0025": "Matemáticas Discretas",
    "MA0026": "Introducción a la Ciencia de Datos",
    "MA0027": "Programación 1",
    "MA0028": "Pensamiento Crítico en Ciencia de Datos",
    "MA0029": "Idioma 1",
    "MA0030": "Cálculo 2",
    "MA0031": "Álgebra Lineal",
    "MA0032": "Programación 2",
    "MA0033": "Ética en Ciencia de Datos",
    "MA0034": "Instituciones Políticas",
    "MA0035": "Idioma 2",
    "MA0036": "Inferencia Estadística",
    "MA0037": "Visualización de Datos",
    "MA0038": "Estructuras de Datos",
    "MA0039": "Seguridad y Privacidad",
    "MA0040": "Introducción a la Economía",
    "MA0041": "Idioma 3",
    "MA0042": "Estadística Bayesiana",
    "MA0043": "Data Mining",
    "MA0044": "Bases de Datos",
    "MA0045": "Pensamiento Critico 2",
    "MA0046": "Disciplina 1",
    "MA0047": "Idioma 4",
    "MA0048": "Optimización",
    "MA0049": "Modelos Lineales",
    "MA0050": "Big Data",
    "MA0051": "Desarrollo de Software en Equipo",
    "MA0052": "Disciplina 2",
    "MA0053": "Idioma 5",
    "MA0054": "Statistical Learning",
    "MA0055": "Taller de Habilidades Gerenciales",
    "MA0056": "Proyecto 1",
    "MA0057": "Disciplina 3",
    "MA0058": "Idioma 6",
    "MA0059": "Práctica",
    "MA0060": "Deep Learning",
    "MA0061": "Proyecto 2",
    "MA0062": "Emprendimiento",
    "MA0063": "Disciplina 4",

    # --- Compartida entre ambos planes ---
    "MA0001": "Pre Cálculo",

    # --- Plan vigente (MA0100-MA0145) — coincide con SEMESTRES/PRERREQUISITOS ---
    "MA0100": "Cálculo 1",
    "MA0101": "Matemáticas Discretas",
    "MA0102": "Introducción a la Ciencia de Datos",
    "MA0103": "Programación 1",
    "MA0104": "Pensamiento Crítico en Ciencia de Datos",
    "MA0105": "Idioma 1",
    "MA0106": "Instituciones Políticas",
    "MA0107": "Cálculo 2",
    "MA0108": "Álgebra Lineal",
    "MA0109": "Programación 2",
    "MA0110": "Ética en Ciencia de Datos",
    "MA0111": "Idioma 2",
    "MA0112": "Probabilidad",
    "MA0113": "Fundamentos de Estadística y Programación",
    "MA0115": "Inferencia Estadística",
    "MA0116": "Data Mining",
    "MA0117": "Estructuras de Datos",
    "MA0118": "Seguridad y Privacidad",
    "MA0119": "Introducción a la Economía",
    "MA0120": "Idioma 3",
    "MA0121": "Estadística Bayesiana",
    "MA0122": "Machine Learning 1",
    "MA0123": "Bases de Datos",
    "MA0124": "Pensamiento Critico 2",
    "MA0125": "Disciplina 1",
    "MA0126": "Idioma 4",
    "MA0127": "Visualización 1",
    "MA0128": "Machine Learning 2",
    "MA0129": "Big Data",
    "MA0130": "Emprendimiento",
    "MA0131": "Métodos Numéricos",
    "MA0132": "Disciplina 2",
    "MA0133": "Idioma 5",
    "MA0134": "Optimización",
    "MA0135": "Visualización 2",
    "MA0136": "Formulación de Proyectos",
    "MA0137": "Deep Learning",
    "MA0138": "Disciplina 3",
    "MA0139": "Idioma 6",
    "MA0140": "Práctica",
    "MA0141": "Taller de Habilidades Profesionales",
    "MA0142": "Proyecto",
    "MA0143": "Taller de Habilidades Gerenciales",
    "MA0144": "Disciplina 4",
    "MA0145": "Ciberseguridad",
}


def normalizar_codigo(codigo: str) -> str:
    """Limpia un código tal como venga del Excel: espacios, minúsculas,
    ceros faltantes no se corrigen (eso sería adivinar), solo se
    normaliza mayúsculas/espacios para que 'ma0100 ' == 'MA0100'."""
    return str(codigo).strip().upper()


def nombre_materia(codigo: str) -> str:
    """Nombre estandarizado para mostrar en pantalla/Excel. Si el
    código no está en el catálogo, se devuelve el código tal cual (no
    truena la app, pero queda visible que falta registrarlo)."""
    return CATALOGO_MATERIAS.get(normalizar_codigo(codigo), str(codigo).strip())


def es_codigo_conocido(codigo: str) -> bool:
    return normalizar_codigo(codigo) in CATALOGO_MATERIAS
