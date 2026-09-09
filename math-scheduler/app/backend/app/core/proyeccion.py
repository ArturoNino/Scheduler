"""
Módulo de proyección académica.

Convierte un dataset "crudo" de matrícula (estudiantes actuales, % de
pérdida, inscritos nuevos) en el dataset que consume el solver
(nombre_materia, numero_sesiones, Cantidad_sesiones_computo, No_grupos).

Es el mismo código de `COD_COMPLETO_PROYECCION.ipynb` (clase
`ProyectorUnificado`), portado tal cual, más una función nueva
(`generar_dataset_solver`) que hace el paso que antes hacías a mano:
combinar el resultado de la proyección (que da No_grupos) con un
catálogo fijo de sesiones por materia, para calcular:

    numero_sesiones           = No_grupos * sesiones_por_grupo
    Cantidad_sesiones_computo = No_grupos * sesiones_computo_por_grupo
    division                  = sesiones_por_grupo   (= numero_sesiones // No_grupos)

Este último paso asume que el número de sesiones semanales por grupo
(teóricas y de cómputo) es un valor fijo del currículo, no algo que
dependa de la cantidad de estudiantes. Si esa regla cambia, solo hay
que tocar `generar_dataset_solver`.

ESTANDARIZACIÓN POR CÓDIGO: a partir de esta versión, "Materia" en todo
este módulo (SEMESTRES, PRERREQUISITOS, el input, el catálogo de
sesiones) es el CÓDIGO de la materia (MA####), no el nombre en texto
libre. Esto elimina los problemas de tildes/mayúsculas/variantes de
escritura del mismo nombre. Ver `materias.py` para el catálogo
código -> nombre y la función `nombre_materia()` que resuelve el
nombre bonito solo para mostrar en pantalla/Excel.
"""

from __future__ import annotations

import math

import pandas as pd

from app.core.materias import CATALOGO_MATERIAS, es_codigo_conocido, nombre_materia, normalizar_codigo

# =====================================================================
# 1) Catálogos del currículo (semestres + prerrequisitos) — por CÓDIGO
# =====================================================================

SEMESTRES = {
    1: ["MA0001", "MA0100", "MA0101", "MA0102", "MA0103", "MA0106", "MA0104", "MA0105"],
    2: ["MA0107", "MA0108", "MA0112", "MA0109", "MA0110", "MA0113", "MA0111"],
    3: ["MA0115", "MA0116", "MA0117", "MA0119", "MA0118", "MA0120"],
    4: ["MA0121", "MA0122", "MA0123", "MA0125", "MA0124", "MA0126"],
    5: ["MA0127", "MA0131", "MA0128", "MA0129", "MA0132", "MA0130", "MA0133"],
    6: ["MA0135", "MA0134", "MA0137", "MA0136", "MA0138", "MA0139"],
    7: ["MA0140"],
    8: ["MA0141", "MA0145", "MA0142", "MA0144", "MA0143"],
}
# Referencia (código -> nombre, para leer la tabla de arriba):
#   MA0001 Pre Cálculo          MA0100 Cálculo 1              MA0101 Matemáticas Discretas
#   MA0102 Introd. Ciencia Datos MA0103 Programación 1         MA0104 Pens. Crítico Cs. Datos
#   MA0105 Idioma 1             MA0106 Instituciones Políticas MA0107 Cálculo 2
#   MA0108 Álgebra Lineal       MA0109 Programación 2          MA0110 Ética Cs. Datos
#   MA0111 Idioma 2             MA0112 Probabilidad            MA0113 Fund. Estadística y Prog.
#   MA0115 Inferencia Estad.    MA0116 Data Mining             MA0117 Estructuras de Datos
#   MA0118 Seguridad y Privac.  MA0119 Introd. Economía        MA0120 Idioma 3
#   MA0121 Estadística Bayes.   MA0122 Machine Learning 1      MA0123 Bases de Datos
#   MA0124 Pens. Crítico 2      MA0125 Disciplina 1            MA0126 Idioma 4
#   MA0127 Visualización 1      MA0128 Machine Learning 2      MA0129 Big Data
#   MA0130 Emprendimiento       MA0131 Métodos Numéricos       MA0132 Disciplina 2
#   MA0133 Idioma 5             MA0134 Optimización            MA0135 Visualización 2
#   MA0136 Formulación Proyect. MA0137 Deep Learning           MA0138 Disciplina 3
#   MA0139 Idioma 6             MA0140 Práctica                MA0141 Taller Hab. Profesionales
#   MA0142 Proyecto             MA0143 Taller Hab. Gerenciales MA0144 Disciplina 4
#   MA0145 Ciberseguridad

PRERREQUISITOS = {
    "MA0107": ["MA0100"],  # Cálculo 2 <- Cálculo 1
    "MA0115": ["MA0112"],  # Inferencia Estadística <- Probabilidad
    "MA0121": ["MA0115", "MA0103", "MA0107"],  # Estadística Bayesiana
    "MA0135": ["MA0127", "MA0115", "MA0123"],  # Visualización 2
    "MA0108": ["MA0101"],  # Álgebra Lineal <- Matemáticas Discretas
    "MA0134": ["MA0131"],  # Optimización <- Métodos Numéricos
    "MA0112": ["MA0102"],  # Probabilidad <- Introducción a la Ciencia de Datos
    "MA0116": ["MA0112", "MA0103"],  # Data Mining
    "MA0122": ["MA0116"],  # Machine Learning 1 <- Data Mining
    "MA0128": ["MA0122"],  # Machine Learning 2 <- Machine Learning 1
    "MA0137": ["MA0128"],  # Deep Learning <- Machine Learning 2
    "MA0109": ["MA0103"],  # Programación 2 <- Programación 1
    "MA0117": ["MA0109"],  # Estructuras de Datos <- Programación 2
    "MA0123": ["MA0117"],  # Bases de Datos <- Estructuras de Datos
    "MA0129": ["MA0123", "MA0116"],  # Big Data
    "MA0136": ["MA0124"],  # Formulación de Proyectos <- Pensamiento Crítico 2
    "MA0124": ["MA0104"],  # Pensamiento Crítico 2 <- Pensamiento Crítico Cs. Datos
    "MA0142": ["MA0136"],  # Proyecto <- Formulación de Proyectos
    "MA0132": ["MA0125"],  # Disciplina 2 <- Disciplina 1
    "MA0138": ["MA0132"],  # Disciplina 3 <- Disciplina 2
    "MA0144": ["MA0138"],  # Disciplina 4 <- Disciplina 3
    "MA0111": ["MA0105"],  # Idioma 2 <- Idioma 1
    "MA0120": ["MA0111"],  # Idioma 3 <- Idioma 2
    "MA0126": ["MA0120"],  # Idioma 4 <- Idioma 3
    "MA0133": ["MA0126"],  # Idioma 5 <- Idioma 4
    "MA0139": ["MA0133"],  # Idioma 6 <- Idioma 5
}

COLUMNAS_REQUERIDAS_INPUT = ["Materia", "Estudiantes_Actuales", "Porcentaje_Perdida"]
COLUMNAS_REQUERIDAS_CATALOGO = [
    "Materia",
    "Sesiones_por_grupo",
    "Sesiones_computo_por_grupo",
]


# =====================================================================
# 2) Limpieza de nombres de materia (mismas reglas de la celda 7)
# =====================================================================

_MINUSCULAS = {"a", "de", "del", "la", "las", "el", "los", "y", "o", "en", "con", "para", "por"}

_REEMPLAZOS = {
    "DISCIPLINAS": "DISCIPLINA",
    "PRECALCULO": "Pre Cálculo",
    "IDIOMAS 6": "Idioma 6",
    "INTRODUCCION A LA ECONOMIA": "Introducción a la Economía",
    "PENSAMENTO CRÍTICO EN LA CIENCA DE DATOS": "Pensamiento Crítico en Ciencia de Datos",
}


def _titulo_espanol(texto: str) -> str:
    palabras = texto.lower().split()
    resultado = []
    for i, p in enumerate(palabras):
        resultado.append(p if (p in _MINUSCULAS and i != 0) else p.capitalize())
    return " ".join(resultado)


def normalizar_nombres_materia(df: pd.DataFrame, columna: str = "Materia") -> pd.DataFrame:
    """Aplica las mismas correcciones de texto de tu notebook (typos
    conocidos del dataset real) y normaliza a Título Español."""
    df = df.copy()
    for buscado, reemplazo in _REEMPLAZOS.items():
        df[columna] = df[columna].astype(str).str.replace(buscado, reemplazo, regex=False)
    df[columna] = df[columna].apply(_titulo_espanol)
    return df


# =====================================================================
# 2.1) Input unificado: un solo archivo con matrícula + sesiones
# =====================================================================
# Columnas esperadas (nombres flexibles, no importa mayúsculas/espacios):
#   materias, estudiantes_actuales, porcentaje_perdida, inscritos_nuevos,
#   computo, teoricos, sesiones por grupo
#
# "computo"  -> sesiones de cómputo que necesita CADA grupo, por semana
# "teoricos" -> sesiones teóricas que necesita CADA grupo, por semana
# "sesiones por grupo" -> total de sesiones por grupo (si no viene, se
#                          calcula como teoricos + computo)

_ALIAS_COLUMNAS_UNIFICADO = {
    "materias": "Materia",
    "materia": "Materia",
    "nombre_materia": "Materia",
    "codigo": "Materia",
    "código": "Materia",
    "codigo_materia": "Materia",
    "código_materia": "Materia",
    "clave": "Materia",
    "estudiantes_actuales": "Estudiantes_Actuales",
    "estudiantes actuales": "Estudiantes_Actuales",
    "porcentaje_perdida": "Porcentaje_Perdida",
    "porcentaje perdida": "Porcentaje_Perdida",
    "%_perdida": "Porcentaje_Perdida",
    "inscritos_nuevos": "Inscritos_Nuevos",
    "inscritos nuevos": "Inscritos_Nuevos",
    "computo": "Sesiones_computo_por_grupo",
    "cómputo": "Sesiones_computo_por_grupo",
    "teoricos": "Sesiones_teoricas_por_grupo",
    "teóricos": "Sesiones_teoricas_por_grupo",
    "sesiones_por_grupo": "Sesiones_por_grupo",
    "sesiones por grupo": "Sesiones_por_grupo",
}

COLUMNAS_MINIMAS_UNIFICADO = [
    "Materia",
    "Estudiantes_Actuales",
    "Porcentaje_Perdida",
    "Sesiones_computo_por_grupo",
]


def _normalizar_encabezados(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={k: v for k, v in _ALIAS_COLUMNAS_UNIFICADO.items() if k in df.columns})
    return df


def _parsear_porcentaje(valor) -> float:
    """Acepta 37, 37.0, '37%', '37,5%', 0.37, etc."""
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "").replace(",", ".")
    return float(valor)


def preparar_input_unificado(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Valida y normaliza el archivo único subido por el usuario, dejando
    las columnas internas que usan proyectar()/dividir_grupos() y el
    catálogo de sesiones.

    La columna "Materia" ahora debe traer el CÓDIGO de la materia
    (MA####), no el nombre en texto libre. Se normaliza (mayúsculas,
    sin espacios) y se valida contra el catálogo — si hay un código
    desconocido, se avisa con claridad en vez de dejarlo pasar en
    silencio (eso sería el mismo problema de antes, solo que con
    códigos mal escritos en vez de nombres mal escritos)."""
    df = _normalizar_encabezados(df_raw)

    faltantes = [c for c in COLUMNAS_MINIMAS_UNIFICADO if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Faltan columnas en el archivo: {', '.join(faltantes)}. "
            f"Columnas encontradas: {', '.join(df_raw.columns.astype(str))}"
        )

    df["Materia"] = df["Materia"].apply(normalizar_codigo)

    desconocidos = sorted({c for c in df["Materia"] if not es_codigo_conocido(c)})
    if desconocidos:
        raise ValueError(
            "Estos códigos de materia no están en el catálogo (revisa "
            f"que estén bien escritos, formato MA####): {', '.join(desconocidos)}"
        )

    if "Inscritos_Nuevos" not in df.columns:
        df["Inscritos_Nuevos"] = 0

    df["Porcentaje_Perdida"] = df["Porcentaje_Perdida"].apply(_parsear_porcentaje)
    df["Sesiones_computo_por_grupo"] = df["Sesiones_computo_por_grupo"].fillna(0).astype(float)

    if "Sesiones_por_grupo" not in df.columns:
        if "Sesiones_teoricas_por_grupo" not in df.columns:
            raise ValueError(
                "Falta 'sesiones por grupo' (o, en su defecto, 'teoricos' "
                "para calcularla como teoricos + computo)."
            )
        df["Sesiones_por_grupo"] = (
            df["Sesiones_teoricas_por_grupo"].fillna(0).astype(float)
            + df["Sesiones_computo_por_grupo"]
        )
    else:
        df["Sesiones_por_grupo"] = df["Sesiones_por_grupo"].astype(float)

    return df


# =====================================================================
# 3) Proyector (idéntico a tu clase ProyectorUnificado)
# =====================================================================

class ProyectorUnificado:
    MATERIAS_MAX20 = {
        "MA0001",  # Pre Cálculo
        "MA0100",  # Cálculo 1
        "MA0107",  # Cálculo 2
        "MA0101",  # Matemáticas Discretas
        "MA0108",  # Álgebra Lineal
        "MA0112",  # Probabilidad
        "MA0103",  # Programación 1
        "MA0109",  # Programación 2
        "MA0115",  # Inferencia Estadística
        "MA0116",  # Data Mining
        "MA0117",  # Estructuras de Datos
        "MA0121",  # Estadística Bayesiana
        "MA0122",  # Machine Learning 1
        "MA0128",  # Machine Learning 2
        "MA0123",  # Bases de Datos
        "MA0131",  # Métodos Numéricos
        "MA0129",  # Big Data
        "MA0134",  # Optimización
        "MA0137",  # Deep Learning
    }

    def __init__(self, semestres: dict, prerrequisitos: dict, redondeo: str = "round"):
        self.semestres = semestres
        self.prerrequisitos = prerrequisitos
        self.redondeo = redondeo
        self.ultimas_advertencias: list[str] = []

    def _pct_to_decimal(self, p):
        p = float(p)
        if p < 0:
            p = 0.0
        if p > 1:
            p = p / 100.0
        return p

    def _rnd(self, x):
        if self.redondeo == "ceil":
            return int(math.ceil(float(x)))
        return int(round(float(x)))

    def _semestre_materia(self, materia: str):
        for s, mats in self.semestres.items():
            if materia in mats:
                return s
        return None

    def _proyeccion_sin_prerreq_desde_semestre_anterior(
        self, semestre, perdieron: int, nuevos: int, df: pd.DataFrame
    ) -> int:
        if semestre is None or semestre <= 1:
            return int(perdieron + nuevos)

        semestre_anterior = semestre - 1
        materias_sem_anterior = self.semestres.get(semestre_anterior, [])
        df_sem_anterior = df[df["Materia"].isin(materias_sem_anterior)].copy()

        if df_sem_anterior.empty:
            mayor_aprobado_sem_anterior = 0
        else:
            mayor_aprobado_sem_anterior = df_sem_anterior["Aprobaron"].astype(float).max()

        return int(self._rnd(mayor_aprobado_sem_anterior) + perdieron + nuevos)

    def proyectar(self, df_input: pd.DataFrame) -> pd.DataFrame:
        df = df_input.copy()

        rename_map = {
            "Estudiantes Actuales": "Estudiantes_Actuales",
            "% Pérdida": "Porcentaje_Perdida",
            "Estudiantes_actuales": "Estudiantes_Actuales",
            "porcentaje_perdida": "Porcentaje_Perdida",
            "inscritos_nuevos": "Inscritos_Nuevos",
            "Inscritos nuevos": "Inscritos_Nuevos",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        required = {"Materia", "Estudiantes_Actuales", "Porcentaje_Perdida"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas en df_input: {sorted(missing)}")

        if "Inscritos_Nuevos" not in df.columns:
            df["Inscritos_Nuevos"] = 0

        df["Semestre"] = df["Materia"].astype(str).apply(self._semestre_materia)

        pdec = df["Porcentaje_Perdida"].apply(self._pct_to_decimal)
        df["Perdida_%"] = (pdec * 100).round(2)

        df["Aprobaron"] = (df["Estudiantes_Actuales"].astype(float) * (1 - pdec)).apply(self._rnd)
        df["Perdieron"] = (df["Estudiantes_Actuales"].astype(float) * pdec).apply(self._rnd)

        aprobados_map = dict(zip(df["Materia"].astype(str), df["Aprobaron"].astype(int)))
        codigos_presentes = set(df["Materia"].astype(str))

        self.ultimas_advertencias = []
        filas = []
        for _, r in df.iterrows():
            materia = str(r["Materia"])
            # FIX: pandas convierte "None" a NaN (float) en columnas mixtas
            # con enteros -- "semestre is not None" NUNCA detectaba eso, así
            # que una materia sin semestre conocido (p. ej. un código de un
            # plan viejo que no está en SEMESTRES) se colaba con un
            # semestre "NaN" en vez de cero prerrequisitos limpio.
            semestre = None if pd.isna(r["Semestre"]) else int(r["Semestre"])
            nuevos = int(r["Inscritos_Nuevos"])
            perdieron = int(r["Perdieron"])
            aprobaron = int(r["Aprobaron"])

            lista_prer = self.prerrequisitos.get(materia, [])
            prer_txt = ", ".join(lista_prer) if lista_prer else "Ninguno"

            prer_inmediato = "Ninguno"
            prer_aprob = 0

            if not lista_prer:
                est_proy = self._proyeccion_sin_prerreq_desde_semestre_anterior(
                    semestre=semestre, perdieron=perdieron, nuevos=nuevos, df=df
                )
            else:
                est_proy = perdieron + nuevos
                sem_prer = {}
                for pr in lista_prer:
                    s_pr = self._semestre_materia(pr)
                    if s_pr is not None:
                        sem_prer[pr] = s_pr

                candidatos = [s for s in sem_prer.values() if semestre is not None and s < semestre]
                if candidatos:
                    semestre_cercano = max(candidatos)
                    prer_cercanos = [pr for pr, s in sem_prer.items() if s == semestre_cercano]
                    prer_inmediato = ", ".join(prer_cercanos) if prer_cercanos else "Ninguno"

                    faltantes = [pr for pr in prer_cercanos if pr not in codigos_presentes]
                    if faltantes:
                        self.ultimas_advertencias.append(
                            f"{materia} ({nombre_materia(materia)}) necesita el prerrequisito "
                            f"{', '.join(f'{p} ({nombre_materia(p)})' for p in faltantes)}, "
                            "pero ese código no está en el archivo subido (¿usaste el código de "
                            "otro plan para esa materia?). Se contó como 0 aprobados en ese "
                            "prerrequisito."
                        )

                    prer_aprob = sum(aprobados_map.get(pr, 0) for pr in prer_cercanos)
                    est_proy = prer_aprob + perdieron + nuevos

            filas.append({
                "Semestre": semestre if semestre is not None else 999,
                "Materia": materia,
                "Estudiantes_Actuales": int(r["Estudiantes_Actuales"]),
                "Inscritos_Nuevos": nuevos,
                "Perdida_%": float(r["Perdida_%"]),
                "Aprobaron": aprobaron,
                "Perdieron": perdieron,
                "Prerrequisitos": prer_txt,
                "Prerrequisito_Inmediato": prer_inmediato,
                "Prerrequisitos_Aprobados": int(prer_aprob),
                "Estudiantes_Proyectados": int(est_proy),
            })

        out = pd.DataFrame(filas).sort_values(["Semestre", "Materia"]).reset_index(drop=True)
        return out

    def dividir_grupos(
        self, df_proyeccion: pd.DataFrame, cap_otras: int = 35, cap_core: int = 20
    ) -> pd.DataFrame:
        base = df_proyeccion.copy()
        if not {"Materia", "Estudiantes_Proyectados"}.issubset(base.columns):
            raise ValueError("Se necesita 'Materia' y 'Estudiantes_Proyectados'.")

        caps, ng, sizes_col = [], [], []
        for _, r in base.iterrows():
            materia = str(r["Materia"])
            n = int(r["Estudiantes_Proyectados"] or 0)
            cap = int(cap_core) if materia in self.MATERIAS_MAX20 else int(cap_otras)

            if n <= 0:
                grupos, sizes = 0, []
            else:
                grupos = math.ceil(n / cap)
                base_size = n // grupos
                extra = n % grupos
                sizes = [base_size + 1] * extra + [base_size] * (grupos - extra)

            caps.append(cap)
            ng.append(grupos)
            sizes_col.append(sizes)

        base["Capacidad_usada"] = caps
        base["No_grupos"] = ng
        base["Tamaños_grupos"] = sizes_col
        return base


# =====================================================================
# 4) Generación del dataset final para el solver
# =====================================================================

def validar_catalogo_sesiones(df_catalogo: pd.DataFrame) -> list[str]:
    errores = []
    faltantes = [c for c in COLUMNAS_REQUERIDAS_CATALOGO if c not in df_catalogo.columns]
    if faltantes:
        errores.append(f"Faltan columnas en el catálogo de sesiones: {', '.join(faltantes)}")
    return errores


def generar_dataset_solver(
    df_input: pd.DataFrame,
    df_catalogo: pd.DataFrame,
    cap_otras: int = 35,
    cap_core: int = 20,
    redondeo: str = "round",
    limpiar_nombres: bool = True,
) -> dict:
    """Corre proyección + división de grupos + combinación con el
    catálogo de sesiones, y arma el dataset que espera el solver.

    df_input: Materia (código MA####), Estudiantes_Actuales,
              Porcentaje_Perdida, Inscritos_Nuevos (opcional).
    df_catalogo: Materia (código MA####), Sesiones_por_grupo,
              Sesiones_computo_por_grupo (valores fijos del currículo,
              no dependen de matrícula).
    cap_core: tope de estudiantes por grupo para las materias "core"
              (Cálculo, Programación, Machine Learning, etc. — la lista
              fija en ProyectorUnificado.MATERIAS_MAX20). Antes era 20
              fijo, ahora se puede ajustar desde la interfaz.
    cap_otras: tope de estudiantes por grupo para el resto de materias.
    limpiar_nombres: normaliza los códigos (mayúsculas, sin espacios).

    Retorna un dict con:
      - proyeccion_detallada: salida completa de proyectar()+dividir_grupos(),
        con "Materia" = código y "Materia_Nombre" = nombre estandarizado
      - dataset_solver: nombre_materia (código), materia_nombre,
        numero_sesiones, Cantidad_sesiones_computo, No_grupos, division
      - materias_sin_catalogo: códigos proyectados que no tenían fila en
        el catálogo de sesiones (quedan con 0 sesiones, hay que
        completarlas a mano)
    """
    df_in = df_input.copy()
    if limpiar_nombres:
        df_in["Materia"] = df_in["Materia"].apply(normalizar_codigo)

    proy = ProyectorUnificado(SEMESTRES, PRERREQUISITOS, redondeo=redondeo)
    df_proy = proy.proyectar(df_in)
    df_grupos = proy.dividir_grupos(df_proy, cap_otras=cap_otras, cap_core=cap_core)
    df_grupos.insert(1, "Materia_Nombre", df_grupos["Materia"].apply(nombre_materia))

    df_cat = df_catalogo.copy()
    if limpiar_nombres:
        df_cat["Materia"] = df_cat["Materia"].apply(normalizar_codigo)
    df_cat = df_cat[COLUMNAS_REQUERIDAS_CATALOGO].drop_duplicates(subset=["Materia"])

    merged = df_grupos.merge(df_cat, on="Materia", how="left")

    materias_sin_catalogo = merged.loc[
        merged["Sesiones_por_grupo"].isna(), "Materia"
    ].apply(nombre_materia).tolist()

    merged["Sesiones_por_grupo"] = merged["Sesiones_por_grupo"].fillna(0)
    merged["Sesiones_computo_por_grupo"] = merged["Sesiones_computo_por_grupo"].fillna(0)

    merged["numero_sesiones"] = (merged["No_grupos"] * merged["Sesiones_por_grupo"]).astype(int)
    merged["Cantidad_sesiones_computo"] = (
        merged["No_grupos"] * merged["Sesiones_computo_por_grupo"]
    ).astype(int)
    merged["division"] = merged["Sesiones_por_grupo"].astype(int)

    dataset_solver = merged.rename(columns={"Materia": "nombre_materia", "Materia_Nombre": "materia_nombre"})[
        ["nombre_materia", "materia_nombre", "numero_sesiones", "Cantidad_sesiones_computo", "No_grupos", "division"]
    ]
    # El solver solo necesita materias con al menos un grupo proyectado.
    dataset_solver = dataset_solver[dataset_solver["No_grupos"] > 0].reset_index(drop=True)

    return dict(
        proyeccion_detallada=df_grupos,
        dataset_solver=dataset_solver,
        materias_sin_catalogo=materias_sin_catalogo,
        advertencias_prerrequisitos=proy.ultimas_advertencias,
    )


def generar_dataset_solver_unificado(
    df_raw: pd.DataFrame,
    cap_otras: int = 35,
    cap_core: int = 20,
    redondeo: str = "round",
    limpiar_nombres: bool = True,
) -> dict:
    """Punto de entrada nuevo: recibe el archivo único (matrícula +
    sesiones por grupo en las mismas filas) y hace todo el pipeline."""
    df_prep = preparar_input_unificado(df_raw)

    df_matricula = df_prep[["Materia", "Estudiantes_Actuales", "Porcentaje_Perdida", "Inscritos_Nuevos"]]
    df_catalogo = df_prep[["Materia", "Sesiones_por_grupo", "Sesiones_computo_por_grupo"]]

    return generar_dataset_solver(
        df_input=df_matricula,
        df_catalogo=df_catalogo,
        cap_otras=cap_otras,
        cap_core=cap_core,
        redondeo=redondeo,
        limpiar_nombres=limpiar_nombres,
    )
