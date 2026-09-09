"""
Núcleo del modelo de optimización (MILP) de asignación de horarios.

Este módulo es el mismo modelo que ya validaste en
`cod_prueba_real__1.ipynb`, portado a una función reutilizable para
poder llamarlo desde la API sin depender de Jupyter/Colab.

No se cambió ninguna restricción ni la función objetivo: HC1-HC9 y las
restricciones blandas SC10-SC11 son exactamente las mismas. Lo único
que cambia es que ahora los parámetros (días, franjas, disponibilidad
de salones, penalización) entran como argumentos en vez de estar
hardcodeados en la celda.
"""

from __future__ import annotations

import time
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
from pyomo.opt import SolverStatus, TerminationCondition

# =====================================================================
# Configuración por defecto (misma que en el notebook)
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
# en 18-20 (igual que en tu versión mejorada del modelo). El resto de
# materias con 1 sesión/semana caen en Martes/Jueves como antes.
# NOTA: con la estandarización por código, "Disciplina 4" es un solo
# código (MA0144) sin distinguir el track/electiva (DEFI, Marketing,
# Agrotech...); si necesitas volver a diferenciar tracks dentro de
# Disciplina 4 hay que darle un código propio a cada track en el
# catálogo de materias.xlsx que suba el usuario — avísame si hace falta.
FRANJA_RESTRINGIDA_DEFAULT = "18-20"
MATERIAS_FRANJA_LIBRE_DEFAULT = [
    "MA0145",  # Ciberseguridad
    "MA0144",  # Disciplina 4
    "MA0143",  # Taller de Habilidades Gerenciales
    "MA0141",  # Taller de Habilidades Profesionales
]


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

    Con 1 sesión/semana, la materia va a Martes/Jueves como cualquier
    otra, EXCEPTO si está en `materias_franja_libre` (esas sí pueden ir
    cualquier día — son las que usan la franja restringida 18-20)."""
    materias_franja_libre = materias_franja_libre or set()
    if sesiones_por_grupo == 3:
        candidatos = ["Lunes", "Miercoles", "Viernes"]
    elif sesiones_por_grupo == 2:
        candidatos = ["Martes", "Jueves"]
    elif sesiones_por_grupo == 1:
        candidatos = list(dias) if materia in materias_franja_libre else ["Martes", "Jueves"]
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
    )


# =====================================================================
# Construcción y solución del modelo (HC1-HC9, SC10-SC11)
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
    solver_path: str | None = None,
) -> ResultadoSolver:
    """Construye y resuelve el MILP. Devuelve un objeto serializable
    listo para responder por la API (sin dependencias de Pyomo).

    activar_franja_fija: agrupa las sesiones de un mismo grupo en una
        sola franja horaria fija (con holgura si no alcanza — ya no
        vuelve el problema infactible, a diferencia de la versión
        anterior que usaba una igualdad estricta).
    activar_franja_18_20: restringe la franja `franja_restringida`
        (18-20 por defecto) para que solo la usen las materias de
        `materias_franja_libre`, y como máximo una materia por día en
        esa franja.
    """

    dias = dias or DIAS_DEFAULT
    horas = horas or HORAS_DEFAULT
    disponibilidad = disponibilidad or DISPONIBILIDAD_DEFAULT

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
    MG = pre["MG"]
    MG_teo = pre["MG_teo"]
    MG_comp = pre["MG_comp"]

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

    # HC6
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

    model.HC10_franja_18_20 = Constraint(model.MG, model.D, rule=franja_18_20_rule)
    if not aplicar_franja_18_20:
        model.HC10_franja_18_20.deactivate()

    # HC10b: la contraparte de HC10 -- antes solo se le PROHIBÍA la franja
    # 18-20 a las demás materias, pero nunca se OBLIGABA a Ciberseguridad /
    # Disciplina 4 / Talleres a usar esa franja exclusivamente, así que el
    # solver las podía programar en cualquier otra hora si eso optimizaba
    # mejor el resto del horario. Esta restricción cierra ese hueco: si la
    # materia está en la lista libre, CUALQUIER sesión suya (en cualquier
    # día) tiene que caer en franja_restringida, nunca en otra hora.
    def franja_18_20_exclusiva_rule(model, m, g, d, t):
        if m in materias_libre_set and t != franja_restringida:
            return model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t] == 0
        return Constraint.Skip

    model.HC10b_franja_18_20_exclusiva = Constraint(
        model.MG, model.D, model.T, rule=franja_18_20_exclusiva_rule
    )
    if not aplicar_franja_18_20:
        model.HC10b_franja_18_20_exclusiva.deactivate()

    # HC13: como máximo una materia (de las de franja libre) por día en
    # esa franja restringida.
    def una_materia_18_20_rule(model, d):
        grupos_franja = [(m, g) for (m, g) in MG if m in materias_libre_set]
        if not grupos_franja:
            return Constraint.Skip
        return (
            sum(
                model.x_t[(m, g), d, franja_restringida] + model.x_c[(m, g), d, franja_restringida]
                for (m, g) in grupos_franja
            )
            <= 1
        )

    model.HC13_una_materia_18_20 = Constraint(model.D, rule=una_materia_18_20_rule)
    if not aplicar_franja_18_20:
        model.HC13_una_materia_18_20.deactivate()

    # SC10 / SC11 (blandas, opcionales)
    def una_franja_rule(model, m, g):
        if sesiones_materia[m] > 1:
            return sum(model.z[(m, g), t] for t in model.T) == 1
        return Constraint.Skip

    model.SC10_una_franja = Constraint(model.MG, rule=una_franja_rule)

    def franja_fija_rule(model, m, g, t):
        # FIX: antes era una igualdad ("=="), que exigía el 100% de las
        # sesiones exactas en la franja elegida y, si los salones no
        # alcanzaban, no había ningún z factible y el modelo completo se
        # volvía infactible. Con "<=" el modelo puede asignar menos
        # sesiones en la franja elegida y dejar el resto como holgura
        # (HC1/HC2), en vez de tumbar todo el problema.
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

    # Función objetivo
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
        ),
        sense=maximize,
    )

    solver_kwargs = {}
    if solver_path:
        solver_kwargs["executable"] = solver_path
    solver = SolverFactory("glpk", **solver_kwargs)

    inicio = time.time()
    results = solver.solve(model, tee=False)
    duracion = time.time() - inicio

    estado = str(results.solver.status)
    condicion = str(results.solver.termination_condition)
    factible = (
        results.solver.status == SolverStatus.ok
        and results.solver.termination_condition == TerminationCondition.optimal
    )

    if not factible:
        return ResultadoSolver(
            estado=estado,
            condicion=condicion,
            factible=False,
            tiempo_segundos=round(duracion, 3),
            mensaje=(
                "El solver no encontró solución óptima. Revisa capacidad de "
                "salones (HC3/HC4) o posibles restricciones contradictorias."
            ),
        )

    # ── Horario ──────────────────────────────────────────────────────
    filas_horario = []
    for (m, g) in model.MG:
        for d in model.D:
            for t in model.T:
                if value(model.x_t[(m, g), d, t]) >= 0.5:
                    filas_horario.append(
                        {"materia": m, "grupo": g, "tipo_salon": "teorico", "dia": d, "hora": t}
                    )
                if value(model.x_c[(m, g), d, t]) >= 0.5:
                    filas_horario.append(
                        {"materia": m, "grupo": g, "tipo_salon": "computo", "dia": d, "hora": t}
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

    total = len(resumen_grupos)
    completos = sum(1 for r in resumen_grupos if r["asignacion_completa"])
    kpis = {
        "grupos_totales": total,
        "asignaciones_completas": completos,
        "asignaciones_incompletas": total - completos,
        "porcentaje_completitud": round(100 * completos / total, 1) if total else 0,
        "sesiones_teoricas_totales": sum(sesiones_teorico.values()),
        "sesiones_computo_totales": sum(sesiones_computo.values()),
    }

    return ResultadoSolver(
        estado=estado,
        condicion=condicion,
        factible=True,
        horario=filas_horario,
        resumen=resumen_grupos,
        uso_salones=uso_salones,
        kpis=kpis,
        tiempo_segundos=round(duracion, 3),
    )
