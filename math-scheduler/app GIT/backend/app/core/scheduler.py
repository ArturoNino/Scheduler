"""
Núcleo del modelo de optimización (MILP) de asignación de horarios.

Este módulo es el modelo validado en los notebooks (`cod_prueba_real__1.ipynb`
y la clase `SchedulerModel` con las correcciones de los tutores), portado a una
función reutilizable para poder llamarlo desde la API sin depender de Jupyter.

Restricciones del modelo
------------------------
Duras (siempre activas salvo que se indique):
  HC1-HC2    sesiones teóricas / de cómputo requeridas por grupo (con holgura)
  HC3-HC4    capacidad de salones teóricos / salas de cómputo por día-franja
  HC5        máximo una sesión por grupo por día
  HC6-HC7    días permitidos según sesiones/semana
               3 -> Lun-Mié-Vie · 2 -> Mar-Jue · 1 -> Mar-Jue (salvo franja libre)
  HC8-HC9    tipo de salón coherente con el tipo de materia
  HC10/10b   franja 18-20 exclusiva de las materias de "franja libre"
  HC13       como máximo UNA materia de franja libre por día en 18-20
  HC15       Cálculo 1/2, Discretas, Álgebra, Probabilidad, Métodos Numéricos y
             Optimización solo en la mañana (7-13)                    [tutores]
  HC16       Emprendimiento solo Lun-Mié-Vie                          [tutores]
  HC17       Marketing 1-3 solo 9-11                                  [tutores]
  HC18       Healthtech 1-3 entre 9-11 y 14-16                        [tutores]
  HC19       Defi / Estadística / Neurociencias (Disciplinas) solo mañana
                                                                      [tutores]
Blandas (van a la función objetivo):
  SC10-SC11  sesiones de un grupo en una franja fija
  SC12       cruces entre materias del mismo semestre (modo binario/fracción)
  SC13       dispersión: no concentrar todos los grupos de una misma materia en
             el mismo día-franja (K = ceil(grupos / franjas posibles) + holgura_k)
                                                                      [tutores]

Identificador de materia
------------------------
En la app el identificador es el CÓDIGO (MA####). Las reglas de los tutores
están escritas con NOMBRES ("Cálculo 1", "Defi 1", ...), así que se traducen a
los códigos presentes en el dataset a través del catálogo (`materias.py`). Los
nombres que no existen en el dataset se ignoran y quedan reportados en
`ResultadoSolver.avisos` (p. ej. los tracks Marketing/Healthtech/Defi: el
catálogo vigente unifica cada Disciplina en un solo código).
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass, field

import pandas as pd
from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Set,
    SolverFactory,
    Var,
    maximize,
    value,
)

from app.core.materias import nombre_materia


# =====================================================================
# Configuración por defecto
# =====================================================================

DIAS_DEFAULT = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
HORAS_DEFAULT = ["7-9", "9-11", "11-13", "14-16", "16-18", "18-20"]

DISPONIBILIDAD_DEFAULT = {
    "Lunes":     {"teorico": 5, "computo": 4},
    "Martes":    {"teorico": 5, "computo": 4},
    "Miercoles": {"teorico": 5, "computo": 4},
    "Jueves":    {"teorico": 5, "computo": 4},
    "Viernes":   {"teorico": 5, "computo": 4},
}

COLUMNAS_REQUERIDAS = [
    "nombre_materia",
    "numero_sesiones",
    "Cantidad_sesiones_computo",
    "No_grupos",
]

# Franja restringida: por defecto solo estas materias pueden programarse
# en 18-20 (y SOLO ahí, ver HC10b). Se identifican por código.
FRANJA_RESTRINGIDA_DEFAULT = "18-20"
MATERIAS_FRANJA_LIBRE_DEFAULT = [
    "MA0145",  # Ciberseguridad
    "MA0144",  # Disciplina 4
    "MA0143",  # Taller de Habilidades Gerenciales
    "MA0141",  # Taller de Habilidades Profesionales
]

FRANJAS_MANANA = ["7-9", "9-11", "11-13"]

# Restricciones DURAS de franja por materia (correcciones de los tutores).
# nombre de la regla -> (materias por NOMBRE, franjas permitidas).
# Si una materia aparece en varias reglas, sus franjas se intersectan.
RESTRICCIONES_FRANJA_DEFAULT: dict[str, tuple[list[str], list[str]]] = {
    # HC15: solo en la mañana (7:00 - 13:00)
    "HC15_solo_manana": (
        [
            "Calculo 1", "Matematicas Discretas", "Calculo 2", "Algebra Lineal",
            "Probabilidad", "Metodos Numericos", "Optimizacion",
        ],
        FRANJAS_MANANA,
    ),
    # HC17: Marketing 1, 2 y 3 solo 9-11
    "HC17_marketing_9_11": (["Marketing 1", "Marketing 2", "Marketing 3"], ["9-11"]),
    # HC18: Healthtech 1, 2 y 3 desde 9-11 hasta 14-16
    "HC18_healthtech_9_a_16": (
        ["Healthtech 1", "Healthtech 2", "Healthtech 3"],
        ["9-11", "11-13", "14-16"],
    ),
    # HC19: disciplinas Defi, Estadística y Neurociencias solo en la mañana
    "HC19_disciplinas_manana": (
        [
            "Defi 1", "Defi 2", "Defi 3",
            "Estadistica 1", "Estadistica 2", "Estadistica 3",
            "Neurociencias 1", "Neurociencias 2", "Neurociencias 3",
        ],
        FRANJAS_MANANA,
    ),
}

# HC16: materias de 1 sesión/semana que deben ir lunes, miércoles o viernes
# (el patrón por defecto de 1 sesión les daría Martes/Jueves).
MATERIAS_SOLO_LMV_DEFAULT = ["Emprendimiento"]
DIAS_LMV = ["Lunes", "Miercoles", "Viernes"]

# Cómo se penalizan los cruces entre materias del mismo semestre (SC12).
#   binario  -> variable ocupa[m,d,t] (exacto, más pesado para el solver)
#   fraccion -> suma de fracciones de grupos, sin binarias extra (más liviano)
#   ninguno  -> sin control de cruces
MODOS_CRUCE = ("binario", "fraccion", "ninguno")


# =====================================================================
# Utilidades de nombres (para traducir nombre -> código)
# =====================================================================

def _normalizar(nombre) -> str:
    """Mayúsculas y sin tildes, para comparar nombres sin depender de cómo se escribieron."""
    sin_tildes = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.upper().split())


def _clave(nombre) -> str:
    """Como _normalizar pero además sin espacios ni guiones ('Health Tech 1' = 'Healthtech 1')."""
    return re.sub(r"[^A-Z0-9]", "", _normalizar(nombre))


def _buscar_materias(
    nombres: list[str],
    materias: list[str],
    etiqueta: str,
    avisos: list[str],
) -> list[str]:
    """Traduce nombres del catálogo de reglas a los identificadores del dataset.

    `materias` son los identificadores del dataset (códigos MA#### en la app;
    nombres en texto libre si se subió un dataset viejo). Cada uno se compara
    por su NOMBRE ESTANDARIZADO (`nombre_materia`). Se acepta variación de
    tildes/mayúsculas/espacios y nombres que TERMINEN igual si son únicos
    ('Defi 1' -> 'Disciplina 1 - Defi 1'). Los nombres que no aparecen se
    reportan en `avisos` (una línea por regla) y se ignoran.
    """
    por_clave: dict[str, list[str]] = {}
    for m in materias:
        por_clave.setdefault(_clave(nombre_materia(m)), []).append(m)

    encontradas: list[str] = []
    faltantes: list[str] = []
    for n in nombres:
        clave = _clave(n)
        candidatas = list(por_clave.get(clave, []))
        if not candidatas:
            por_sufijo = [m for k, ms in por_clave.items() if k.endswith(clave) for m in ms]
            if len(por_sufijo) == 1:
                candidatas = por_sufijo
        if not candidatas:
            faltantes.append(n)
            continue
        for m in candidatas:
            if m not in encontradas:
                encontradas.append(m)

    if faltantes:
        avisos.append(
            f"({etiqueta}) no están en el dataset y se ignoran: {', '.join(faltantes)}"
        )
    return encontradas


# =====================================================================
# Validación de datos (equivalente al diagnóstico de la celda 4)
# =====================================================================

def validar_dataset(df: pd.DataFrame) -> list[str]:
    """Replica el diagnóstico de consistencia del notebook.

    numero_sesiones y Cantidad_sesiones_computo son totales agregados
    de TODOS los grupos de la materia (no por grupo). El fix de
    dividir por No_grupos se aplica en preprocesar(), aquí solo se
    valida consistencia básica sobre los totales crudos.
    """
    errores: list[str] = []

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        errores.append(
            f"Faltan columnas requeridas en el dataset: {', '.join(faltantes)}"
        )
        return errores

    for _, row in df.iterrows():
        m = row["nombre_materia"]
        ns = int(row["numero_sesiones"])
        nc = int(row["Cantidad_sesiones_computo"])
        ng = int(row["No_grupos"])

        if ng <= 0:
            errores.append(f"{m}: No_grupos debe ser mayor a 0 (tiene {ng})")
            continue
        if nc > ns:
            errores.append(
                f"{m}: Cantidad_sesiones_computo ({nc}) > numero_sesiones ({ns})"
            )
        if ns % ng != 0:
            errores.append(
                f"{m}: numero_sesiones ({ns}) no es divisible exactamente entre "
                f"No_grupos ({ng}); se truncará con división entera"
            )

    return errores


# =====================================================================
# Preprocesamiento (fix numero_sesiones // No_grupos ya incorporado)
# =====================================================================

def _get_dias_permitidos(
    sesiones_por_grupo: int,
    dias: list[str],
    materia: str = "",
    materias_franja_libre: set[str] | None = None,
) -> list[str]:
    """Días permitidos según el número de sesiones semanales del grupo.

    Prioridad:
      1. Materias de franja libre (Ciberseguridad, Disciplina 4, Talleres):
         cualquier día, sin importar cuántas sesiones tengan -- ya quedan
         limitadas a 18-20 por HC10b/HC13, así que no hace falta restringir
         también el día (evita que compitan por Martes/Jueves).
      2. 3 sesiones/semana -> Lunes, Miércoles, Viernes
      3. 1 o 2 sesiones/semana -> Martes, Jueves
         (la de 1 sesión se alinea con el patrón de la programación real;
         Emprendimiento es la excepción y se corrige con HC16.)
      4. Otro caso (4+ sesiones) -> cualquier día
    """
    materias_franja_libre = materias_franja_libre or set()
    if materia in materias_franja_libre:
        candidatos = list(dias)
    elif sesiones_por_grupo == 3:
        candidatos = ["Lunes", "Miercoles", "Viernes"]
    elif sesiones_por_grupo in (1, 2):
        candidatos = ["Martes", "Jueves"]
    else:
        candidatos = list(dias)
    # Filtra contra los días realmente configurados (por si el usuario
    # trabaja con una semana reducida/custom).
    disponibles = [d for d in candidatos if d in dias]
    return disponibles or list(dias)


def preprocesar(
    df: pd.DataFrame,
    dias: list[str],
    materias_franja_libre: set[str] | None = None,
) -> dict:
    materias = df["nombre_materia"].tolist()
    grupos_por_materia: dict[str, list[int]] = {}
    sesiones_materia: dict[str, int] = {}
    sesiones_computo: dict[str, int] = {}
    sesiones_teorico: dict[str, int] = {}
    tipo_sesion: dict[str, str] = {}

    for _, row in df.iterrows():
        m = row["nombre_materia"]
        ng = int(row["No_grupos"])
        # FIX: numero_sesiones y Cantidad_sesiones_computo son totales
        # agregados de todos los grupos -> se dividen por No_grupos
        # para obtener el valor POR GRUPO.
        ns = int(row["numero_sesiones"]) // ng
        nc = int(row["Cantidad_sesiones_computo"]) // ng
        nt = ns - nc

        grupos_por_materia[m] = list(range(ng))
        sesiones_materia[m] = ns
        sesiones_computo[m] = nc
        sesiones_teorico[m] = nt

        if nc == ns:
            tipo_sesion[m] = "computo"
        elif nc == 0:
            tipo_sesion[m] = "teorico"
        else:
            tipo_sesion[m] = "mixta"

    dias_permitidos = {
        m: _get_dias_permitidos(sesiones_materia[m], dias, m, materias_franja_libre)
        for m in materias
    }

    MG = [(m, g) for m in materias for g in grupos_por_materia[m]]
    MG_teo = [(m, g) for (m, g) in MG if sesiones_teorico[m] > 0]
    MG_comp = [(m, g) for (m, g) in MG if sesiones_computo[m] > 0]

    # Semestre de cada materia (columna opcional "semestre" del dataset -- la
    # agrega generar_dataset_solver() a partir del código MA####). Se usa para
    # (a) penalizar cruces dentro de un mismo semestre y (b) el filtro de
    # visualización por semestre del frontend.
    semestre_de: dict[str, int | None] = {m: None for m in materias}
    if "semestre" in df.columns:
        for m, s in zip(df["nombre_materia"], df["semestre"]):
            if not pd.isna(s):
                semestre_de[m] = int(s)

    # Solo interesan los semestres con 2+ materias: uno con una sola materia
    # no puede tener cruces.
    materias_por_semestre: dict[int, list[str]] = {}
    for m, s in semestre_de.items():
        if s is not None:
            materias_por_semestre.setdefault(s, []).append(m)
    materias_por_semestre = {
        s: ms for s, ms in materias_por_semestre.items() if len(ms) > 1
    }

    return dict(
        materias=materias,
        grupos_por_materia=grupos_por_materia,
        sesiones_materia=sesiones_materia,
        sesiones_computo=sesiones_computo,
        sesiones_teorico=sesiones_teorico,
        tipo_sesion=tipo_sesion,
        dias_permitidos=dias_permitidos,
        MG=MG,
        MG_teo=MG_teo,
        MG_comp=MG_comp,
        semestre_de=semestre_de,
        materias_por_semestre=materias_por_semestre,
    )


# =====================================================================
# Construcción y solución del modelo
# =====================================================================

@dataclass
class ResultadoSolver:
    estado: str
    condicion: str
    factible: bool
    horario: list[dict] = field(default_factory=list)
    resumen: list[dict] = field(default_factory=list)
    uso_salones: list[dict] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    tiempo_segundos: float = 0.0
    mensaje: str | None = None


def resolver_horario(
    df: pd.DataFrame,
    dias: list[str] | None = None,
    horas: list[str] | None = None,
    disponibilidad: dict | None = None,
    penalizacion: float = 10,
    activar_franja_fija: bool = True,
    activar_franja_18_20: bool = True,
    franja_restringida: str | None = None,
    materias_franja_libre: list[str] | None = None,
    activar_cruce_semestre: bool = True,
    penalizacion_cruce: float = 5,
    modo_cruce_semestre: str = "binario",
    activar_restricciones_materia: bool = True,
    penalizacion_dispersion: float = 0.5,
    holgura_k: int = 0,
    tiempo_limite_segundos: float = 120,
    mip_rel_gap: float | None = None,
    solver_name: str = "appsi_highs",
    solver_path: str | None = None,
) -> ResultadoSolver:
    """Construye y resuelve el MILP. Devuelve un objeto serializable
    listo para responder por la API (sin dependencias de Pyomo).

    activar_franja_fija: agrupa las sesiones de un mismo grupo en una
        sola franja horaria fija (con holgura si no alcanza -- no vuelve
        el problema infactible).
    activar_franja_18_20: restringe la franja `franja_restringida`
        (18-20 por defecto) para que solo la usen las materias de
        `materias_franja_libre` (HC10/HC10b), con como máximo una materia
        por día en esa franja (HC13).
    activar_cruce_semestre / modo_cruce_semestre / penalizacion_cruce:
        penalizan -sin prohibir- que dos materias del mismo semestre queden
        en el mismo día-hora. `modo_cruce_semestre` elige la formulación:
        "binario" (exacta), "fraccion" (más liviana, sin binarias extra) o
        "ninguno". Con activar_cruce_semestre=False equivale a "ninguno".
    activar_restricciones_materia: aplica HC15-HC19 (franjas por materia,
        correcciones de los tutores) y HC16 (Emprendimiento L-M-V).
    penalizacion_dispersion / holgura_k: SC13. Penaliza concentrar más de
        K grupos de una misma materia en el mismo día-franja, con
        K = ceil(grupos / franjas posibles) + holgura_k. 0 = desactivada;
        debe ser mucho menor que `penalizacion`.
    tiempo_limite_segundos: límite de tiempo del solver; devuelve la mejor
        solución factible encontrada en vez de dejar colgada la petición.
    mip_rel_gap: tolerancia de optimalidad (0.02 = 2%). None = valor del solver.
    solver_name: "appsi_highs" (recomendado) o "glpk" (respaldo).
    """

    dias = dias or DIAS_DEFAULT
    horas = horas or HORAS_DEFAULT
    disponibilidad = disponibilidad or DISPONIBILIDAD_DEFAULT

    if modo_cruce_semestre not in MODOS_CRUCE:
        raise ValueError(
            f"modo_cruce_semestre debe ser uno de {MODOS_CRUCE}, se recibió '{modo_cruce_semestre}'"
        )
    modo_cruce = modo_cruce_semestre if activar_cruce_semestre else "ninguno"

    slots_teorico = {d: int(disponibilidad[d]["teorico"]) for d in dias}
    slots_computo = {d: int(disponibilidad[d]["computo"]) for d in dias}

    franja_restringida = franja_restringida or FRANJA_RESTRINGIDA_DEFAULT
    materias_libre_set = set(
        materias_franja_libre if materias_franja_libre is not None else MATERIAS_FRANJA_LIBRE_DEFAULT
    )
    # Si la franja restringida ni siquiera está en las horas configuradas,
    # la restricción no aplica (no hay nada que restringir).
    aplicar_franja_18_20 = activar_franja_18_20 and franja_restringida in horas

    pre = preprocesar(
        df,
        dias,
        materias_franja_libre=materias_libre_set if aplicar_franja_18_20 else set(),
    )
    materias = pre["materias"]
    sesiones_materia = pre["sesiones_materia"]
    sesiones_computo = pre["sesiones_computo"]
    sesiones_teorico = pre["sesiones_teorico"]
    tipo_sesion = pre["tipo_sesion"]
    dias_permitidos = pre["dias_permitidos"]
    grupos_por_materia = pre["grupos_por_materia"]
    MG = pre["MG"]
    MG_teo = pre["MG_teo"]
    MG_comp = pre["MG_comp"]
    semestre_de = pre["semestre_de"]
    materias_por_semestre = pre["materias_por_semestre"] if modo_cruce != "ninguno" else {}

    # ── Reglas por materia de los tutores (HC15-HC19 y HC16) ─────────
    avisos: list[str] = []
    franjas_permitidas: dict[str, list[str]] = {}
    materias_lmv: list[str] = []
    if activar_restricciones_materia:
        materias_lmv = _buscar_materias(MATERIAS_SOLO_LMV_DEFAULT, materias, "HC16", avisos)
        dias_lmv = [d for d in DIAS_LMV if d in dias] or list(dias)
        for m in materias_lmv:
            dias_permitidos[m] = list(dias_lmv)

        for nombre_regla, (nombres, franjas) in RESTRICCIONES_FRANJA_DEFAULT.items():
            franjas_ok = [t for t in franjas if t in horas]
            encontradas = _buscar_materias(nombres, materias, nombre_regla, avisos)
            if encontradas and not franjas_ok:
                avisos.append(
                    f"({nombre_regla}) ninguna de sus franjas existe en las horas configuradas; se ignora."
                )
                continue
            for m in encontradas:
                previas = franjas_permitidas.get(m, list(horas))
                franjas_permitidas[m] = [t for t in previas if t in franjas_ok]

    def franjas_posibles(m: str) -> list[str]:
        """Franjas donde la materia m puede programarse (HC10/10b/13 y HC15-19)."""
        fr = list(franjas_permitidas.get(m, horas))
        if aplicar_franja_18_20:
            if m in materias_libre_set:
                fr = [t for t in fr if t == franja_restringida]
            else:
                fr = [t for t in fr if t != franja_restringida]
        return fr or list(horas)

    model = ConcreteModel()
    model.MG = Set(initialize=MG, dimen=2)
    model.D = Set(initialize=dias)
    model.T = Set(initialize=horas)

    model.x_t = Var(model.MG, model.D, model.T, domain=Binary)
    model.x_c = Var(model.MG, model.D, model.T, domain=Binary)
    model.z = Var(model.MG, model.T, domain=Binary)

    model.holgura_teo = Var(model.MG, domain=NonNegativeReals)
    model.holgura_comp = Var(model.MG, domain=NonNegativeReals)

    # HC1
    def sesiones_teo_rule(model, m, g):
        return (
            sum(model.x_t[(m, g), d, t] for d in model.D for t in model.T)
            + model.holgura_teo[(m, g)]
            == sesiones_teorico[m]
        )

    model.HC1_ses_teo = Constraint(model.MG, rule=sesiones_teo_rule)

    # HC2
    def sesiones_comp_rule(model, m, g):
        return (
            sum(model.x_c[(m, g), d, t] for d in model.D for t in model.T)
            + model.holgura_comp[(m, g)]
            == sesiones_computo[m]
        )

    model.HC2_ses_comp = Constraint(model.MG, rule=sesiones_comp_rule)

    # HC3
    def cap_teo_rule(model, d, t):
        return sum(model.x_t[(m, g), d, t] for (m, g) in MG_teo) <= slots_teorico[d]

    model.HC3_cap_teo = Constraint(model.D, model.T, rule=cap_teo_rule)

    # HC4
    def cap_comp_rule(model, d, t):
        return sum(model.x_c[(m, g), d, t] for (m, g) in MG_comp) <= slots_computo[d]

    model.HC4_cap_comp = Constraint(model.D, model.T, rule=cap_comp_rule)

    # HC5
    def una_clase_dia_rule(model, m, g, d):
        return (
            sum(model.x_t[(m, g), d, t] for t in model.T)
            + sum(model.x_c[(m, g), d, t] for t in model.T)
        ) <= 1

    model.HC5_una_clase_dia = Constraint(model.MG, model.D, rule=una_clase_dia_rule)

    # HC6 (incluye la corrección HC16 de Emprendimiento: dias_permitidos ya la trae)
    def dias_validos_teo_rule(model, m, g, d, t):
        if d not in dias_permitidos[m]:
            return model.x_t[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC6_dias_validos_teo = Constraint(
        model.MG, model.D, model.T, rule=dias_validos_teo_rule
    )

    # HC7
    def dias_validos_comp_rule(model, m, g, d, t):
        if d not in dias_permitidos[m]:
            return model.x_c[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC7_dias_validos_comp = Constraint(
        model.MG, model.D, model.T, rule=dias_validos_comp_rule
    )

    # HC8
    def solo_teo_rule(model, m, g, d, t):
        if tipo_sesion[m] == "teorico":
            return model.x_c[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC8_solo_teo = Constraint(model.MG, model.D, model.T, rule=solo_teo_rule)

    # HC9
    def solo_comp_rule(model, m, g, d, t):
        if tipo_sesion[m] == "computo":
            return model.x_t[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC9_solo_comp = Constraint(model.MG, model.D, model.T, rule=solo_comp_rule)

    # HC10: la franja restringida (18-20 por defecto) solo la pueden usar
    # las materias de materias_franja_libre.
    def franja_18_20_rule(model, m, g, d):
        if m not in materias_libre_set:
            return (
                model.x_t[(m, g), d, franja_restringida]
                + model.x_c[(m, g), d, franja_restringida]
            ) == 0
        return Constraint.Skip

    if aplicar_franja_18_20:
        model.HC10_franja_18_20 = Constraint(model.MG, model.D, rule=franja_18_20_rule)

    # HC10b: contraparte de HC10 -- las materias de franja libre usan
    # EXCLUSIVAMENTE la franja restringida, nunca otra hora.
    def franja_18_20_exclusiva_rule(model, m, g, d, t):
        if m in materias_libre_set and t != franja_restringida:
            return model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t] == 0
        return Constraint.Skip

    if aplicar_franja_18_20:
        model.HC10b_franja_18_20_exclusiva = Constraint(
            model.MG, model.D, model.T, rule=franja_18_20_exclusiva_rule
        )

    # HC13: como máximo una MATERIA (de las de franja libre) por día en la
    # franja restringida, pero TODOS los grupos de esa materia pueden
    # compartirla el mismo día (u_18_20[m, d] marca si la materia la usa).
    materias_libre_presentes = [m for m in materias if m in materias_libre_set]
    model.M18 = Set(initialize=materias_libre_presentes)
    model.u_18_20 = Var(model.M18, model.D, domain=Binary)

    def link_18_20_rule(model, m, g, d):
        if m in materias_libre_set:
            return (
                model.x_t[(m, g), d, franja_restringida] + model.x_c[(m, g), d, franja_restringida]
            ) <= model.u_18_20[m, d]
        return Constraint.Skip

    def una_materia_18_20_rule(model, d):
        if not materias_libre_presentes:
            return Constraint.Skip
        return sum(model.u_18_20[m, d] for m in model.M18) <= 1

    if aplicar_franja_18_20:
        model.HC13_link_18_20 = Constraint(model.MG, model.D, rule=link_18_20_rule)
        model.HC13_una_materia_18_20 = Constraint(model.D, rule=una_materia_18_20_rule)

    # HC15, HC17, HC18, HC19: franjas permitidas por materia (DURAS).
    # franjas_permitidas ya trae la intersección de todas las reglas que
    # tocan a cada materia; fuera de esas franjas, x = 0 para todos sus grupos.
    mg_franjas = [(m, g) for (m, g) in MG if m in franjas_permitidas]
    model.MG_franjas = Set(initialize=mg_franjas, dimen=2)

    def franjas_materia_rule(model, m, g, d, t):
        if t not in franjas_permitidas[m]:
            return model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC15_19_franjas_materia = Constraint(
        model.MG_franjas, model.D, model.T, rule=franjas_materia_rule
    )

    # SC12: cruces entre materias del mismo semestre (penalizado, no duro).
    # cruce_sem[s,d,t] cuenta cuántas materias del semestre s se pasan de 1
    # coincidiendo en el mismo día-hora (la primera es "gratis").
    materias_con_semestre = sorted({m for ms in materias_por_semestre.values() for m in ms})
    model.SEM = Set(initialize=list(materias_por_semestre.keys()))
    model.M_sem = Set(initialize=materias_con_semestre)
    model.cruce_sem = Var(model.SEM, model.D, model.T, domain=NonNegativeReals)

    if modo_cruce == "binario":
        # ocupa[m,d,t] = 1 si la materia m tiene AL MENOS un grupo con sesión.
        model.ocupa = Var(model.M_sem, model.D, model.T, domain=Binary)

        def link_ocupa_rule(model, m, d, t):
            grupos_m = grupos_por_materia[m]
            return (
                sum(model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t] for g in grupos_m)
                <= len(grupos_m) * model.ocupa[m, d, t]
            )

        model.SC12_link_ocupa = Constraint(model.M_sem, model.D, model.T, rule=link_ocupa_rule)

        def cruce_sem_binario_rule(model, s, d, t):
            return (
                sum(model.ocupa[m, d, t] for m in materias_por_semestre[s]) - 1
                <= model.cruce_sem[s, d, t]
            )

        model.SC12_cruce_sem = Constraint(model.SEM, model.D, model.T, rule=cruce_sem_binario_rule)

    elif modo_cruce == "fraccion":
        # Cada materia aporta la FRACCIÓN de sus grupos que cae en (d,t); hay
        # cruce solo si la suma de fracciones del semestre supera 1.
        def cruce_sem_fraccion_rule(model, s, d, t):
            return (
                sum(
                    sum(
                        model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t]
                        for g in grupos_por_materia[m]
                    )
                    / len(grupos_por_materia[m])
                    for m in materias_por_semestre[s]
                )
                - 1
                <= model.cruce_sem[s, d, t]
            )

        model.SC12_cruce_sem = Constraint(model.SEM, model.D, model.T, rule=cruce_sem_fraccion_rule)

    # SC10 / SC11 (blandas, opcionales)
    def una_franja_rule(model, m, g):
        if sesiones_materia[m] > 1:
            return sum(model.z[(m, g), t] for t in model.T) == 1
        return Constraint.Skip

    model.SC10_una_franja = Constraint(model.MG, rule=una_franja_rule)

    def franja_fija_rule(model, m, g, t):
        # "<=" (no "=="): si los salones no alcanzan, el resto de sesiones
        # queda como holgura (HC1/HC2) en vez de volver infactible el modelo.
        if sesiones_materia[m] > 1:
            return (
                sum(model.x_t[(m, g), d, t] for d in dias_permitidos[m])
                + sum(model.x_c[(m, g), d, t] for d in dias_permitidos[m])
            ) <= sesiones_materia[m] * model.z[(m, g), t]
        return Constraint.Skip

    model.SC11_franja_fija = Constraint(model.MG, model.T, rule=franja_fija_rule)

    if not activar_franja_fija:
        model.SC10_una_franja.deactivate()
        model.SC11_franja_fija.deactivate()

    # SC13: dispersión de grupos de una misma materia entre franjas.
    #   K_m           = ceil(grupos / franjas posibles) + holgura_k
    #   exceso[m,d,t] >= (grupos de m con sesión en (d,t)) - K_m
    # Se cuenta con x_t / x_c (no con z) porque z es solo una cota superior
    # de SC11 y podría quedar en 1 sin sesiones asignadas.
    k_grupos = {
        m: max(
            1,
            math.ceil(len(grupos_por_materia[m]) / max(1, len(franjas_posibles(m)))) + int(holgura_k),
        )
        for m in materias
    }
    materias_dispersion = (
        [m for m in materias if len(grupos_por_materia[m]) > k_grupos[m]]
        if penalizacion_dispersion and penalizacion_dispersion > 0
        else []
    )
    model.M_disp = Set(initialize=materias_dispersion)
    model.exceso = Var(model.M_disp, model.D, model.T, domain=NonNegativeReals)

    def exceso_rule(model, m, d, t):
        return (
            model.exceso[m, d, t]
            >= sum(
                model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t]
                for g in grupos_por_materia[m]
            )
            - k_grupos[m]
        )

    model.SC13_exceso = Constraint(model.M_disp, model.D, model.T, rule=exceso_rule)

    # Función objetivo: maximizar sesiones asignadas, menos penalizaciones
    # por holgura, por cruces de semestre y por dispersión.
    model.obj = Objective(
        expr=(
            sum(
                model.x_t[(m, g), d, t]
                for (m, g) in model.MG
                for d in model.D
                for t in model.T
            )
            + sum(
                model.x_c[(m, g), d, t]
                for (m, g) in model.MG
                for d in model.D
                for t in model.T
            )
            - penalizacion
            * sum(
                model.holgura_teo[(m, g)] + model.holgura_comp[(m, g)]
                for (m, g) in model.MG
            )
            - penalizacion_cruce
            * sum(
                model.cruce_sem[s, d, t]
                for s in model.SEM
                for d in model.D
                for t in model.T
            )
            - (penalizacion_dispersion or 0)
            * sum(
                model.exceso[m, d, t]
                for m in model.M_disp
                for d in model.D
                for t in model.T
            )
        ),
        sense=maximize,
    )

    solver_kwargs = {}
    if solver_path:
        solver_kwargs["executable"] = solver_path
    solver = SolverFactory(solver_name, **solver_kwargs)

    # Límite de tiempo y tolerancia de gap: cada solver los llama distinto.
    # HiGHS usa "time_limit"/"mip_rel_gap"; GLPK usa "tmlim"/"mipgap".
    solver_options = {}
    if tiempo_limite_segundos and tiempo_limite_segundos > 0:
        clave_tiempo = "tmlim" if solver_name == "glpk" else "time_limit"
        solver_options[clave_tiempo] = (
            int(tiempo_limite_segundos) if solver_name == "glpk" else tiempo_limite_segundos
        )
    if mip_rel_gap is not None and mip_rel_gap >= 0:
        clave_gap = "mipgap" if solver_name == "glpk" else "mip_rel_gap"
        solver_options[clave_gap] = mip_rel_gap

    inicio = time.time()
    # load_solutions=False: permite revisar si el solver encontró algo ANTES
    # de intentar cargarlo (si se agotó el tiempo sin solución factible no
    # habría nada que leer).
    results = solver.solve(model, tee=False, options=solver_options, load_solutions=False)
    duracion = time.time() - inicio

    estado = str(results.solver.status)
    condicion = str(results.solver.termination_condition)
    hay_solucion = len(results.solution) > 0
    if hay_solucion:
        model.solutions.load_from(results)

    # Si el tiempo se agotó pero el solver YA tenía una solución entera
    # factible, se acepta (mejor "casi óptima" a tiempo que sin respuesta).
    factible = hay_solucion
    solucion_por_limite_tiempo = hay_solucion and condicion != "optimal"

    if not factible:
        return ResultadoSolver(
            estado=estado,
            condicion=condicion,
            factible=False,
            avisos=avisos,
            tiempo_segundos=round(duracion, 3),
            mensaje=(
                "El solver no encontró ninguna solución factible dentro del "
                "tiempo límite. Revisa capacidad de salones (HC3/HC4), "
                "posibles restricciones contradictorias, o sube el tiempo "
                "límite si el dataset es muy grande."
            ),
        )

    # ── Horario ──────────────────────────────────────────────────────
    filas_horario = []
    for (m, g) in model.MG:
        for d in model.D:
            for t in model.T:
                if value(model.x_t[(m, g), d, t]) >= 0.5:
                    filas_horario.append(
                        {
                            "materia": m, "grupo": g, "tipo_salon": "teorico",
                            "dia": d, "hora": t, "semestre": semestre_de[m],
                        }
                    )
                if value(model.x_c[(m, g), d, t]) >= 0.5:
                    filas_horario.append(
                        {
                            "materia": m, "grupo": g, "tipo_salon": "computo",
                            "dia": d, "hora": t, "semestre": semestre_de[m],
                        }
                    )

    orden_dias = {d: i for i, d in enumerate(dias)}
    orden_horas = {h: i for i, h in enumerate(horas)}
    filas_horario.sort(
        key=lambda r: (r["materia"], r["grupo"], orden_dias[r["dia"]], orden_horas[r["hora"]])
    )

    # ── Resumen por grupo ────────────────────────────────────────────
    resumen_grupos = []
    for (m, g) in model.MG:
        ht = round(value(model.holgura_teo[(m, g)]))
        hc = round(value(model.holgura_comp[(m, g)]))
        completo = ht == 0 and hc == 0

        dias_asig_teo, dias_asig_comp = [], []
        for d in dias_permitidos[m]:
            for t in model.T:
                if value(model.x_t[(m, g), d, t]) >= 0.5:
                    dias_asig_teo.append(f"{d} {t}")
                if value(model.x_c[(m, g), d, t]) >= 0.5:
                    dias_asig_comp.append(f"{d} {t}")

        mensajes = []
        if ht > 0:
            mensajes.append(
                f"Faltan {ht} sesión(es) teórica(s) — sin salones teóricos "
                f"disponibles en {', '.join(dias_permitidos[m])}"
            )
        if hc > 0:
            mensajes.append(
                f"Faltan {hc} sesión(es) de cómputo — salas de cómputo ocupadas "
                f"en todas las franjas de {', '.join(dias_permitidos[m])}"
            )

        resumen_grupos.append(
            {
                "materia": m,
                "grupo": g,
                "semestre": semestre_de[m],
                "sesiones_requeridas": sesiones_materia[m],
                "sesiones_asignadas": sesiones_materia[m] - ht - hc,
                "asignacion_completa": completo,
                "diagnostico": " | ".join(mensajes) if mensajes else None,
                "sesiones_teo_asignadas": dias_asig_teo,
                "sesiones_comp_asignadas": dias_asig_comp,
            }
        )

    # ── Uso de salones por día/franja ───────────────────────────────
    uso_salones = []
    for d in dias:
        for t in horas:
            usados_teo = sum(
                1 for (m, g) in MG_teo if value(model.x_t[(m, g), d, t]) >= 0.5
            )
            usados_comp = sum(
                1 for (m, g) in MG_comp if value(model.x_c[(m, g), d, t]) >= 0.5
            )
            uso_salones.append(
                {
                    "dia": d,
                    "hora": t,
                    "teorico_usados": usados_teo,
                    "teorico_disponibles": slots_teorico[d],
                    "computo_usados": usados_comp,
                    "computo_disponibles": slots_computo[d],
                }
            )

    # ── KPIs ────────────────────────────────────────────────────────
    # cruces_semestre se mide SIEMPRE sobre la solución (aunque el modo de
    # penalización sea "ninguno"): cuántas materias del mismo semestre
    # coinciden de más en el mismo día-hora.
    ocupacion: dict[tuple, set] = {}
    for r in filas_horario:
        s = r["semestre"]
        if s is not None:
            ocupacion.setdefault((s, r["dia"], r["hora"]), set()).add(r["materia"])
    cruces_semestre = sum(max(0, len(ms) - 1) for ms in ocupacion.values())

    total = len(resumen_grupos)
    completos = sum(1 for r in resumen_grupos if r["asignacion_completa"])
    kpis = {
        "grupos_totales": total,
        "asignaciones_completas": completos,
        "asignaciones_incompletas": total - completos,
        "porcentaje_completitud": round(100 * completos / total, 1) if total else 0,
        "sesiones_teoricas_totales": sum(sesiones_teorico.values()),
        "sesiones_computo_totales": sum(sesiones_computo.values()),
        "cruces_semestre": cruces_semestre,
    }

    return ResultadoSolver(
        estado=estado,
        condicion=condicion,
        factible=True,
        horario=filas_horario,
        resumen=resumen_grupos,
        uso_salones=uso_salones,
        kpis=kpis,
        avisos=avisos,
        tiempo_segundos=round(duracion, 3),
        mensaje=(
            "Se alcanzó el tiempo límite antes de que el solver pudiera "
            "certificar que esta es la solución óptima matemática. Es una "
            "solución válida (cumple todas las restricciones), pero podría "
            "existir otra mejor. Sube el tiempo límite, usa el modo de cruce "
            "'fracción' o desactiva la penalización de cruce de semestre si "
            "necesitas la óptima exacta."
            if solucion_por_limite_tiempo
            else None
        ),
    )
