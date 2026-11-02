import difflib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from pyomo.environ import (
    Binary, ConcreteModel, Constraint, NonNegativeReals,
    Objective, Set, SolverFactory, Var, maximize, value,
)
from pyomo.opt import SolverStatus, TerminationCondition


DIAS  = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
HORAS = ["7-9", "9-11", "11-13", "14-16", "16-18","18-20"]

FRANJAS_MANANA = ["7-9", "9-11", "11-13"]


def _normalizar(nombre) -> str:
    """Mayusculas y sin tildes, para comparar nombres sin depender de como se escribieron."""
    sin_tildes = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.upper().split())


def _clave(nombre) -> str:
    """Igual que _normalizar pero ademas sin espacios ni guiones ('Health Tech 1' = 'Healthtech 1')."""
    return re.sub(r"[^A-Z0-9]", "", _normalizar(nombre))


@dataclass
class DisponibilidadSalon:
    dia: str
    slots_teorico: int
    slots_computo: int


@dataclass
class ResultadoScheduler:
    horario: pd.DataFrame
    resumen: pd.DataFrame
    total_grupos: int
    completos: int
    incompletos: int


class SchedulerModel:
    """
    MILP para asignacion de horarios academicos (Pyomo; solver HiGHS o GLPK).
    Maximiza sesiones asignadas respetando capacidad de salones teoricos y de computo,
    las restricciones institucionales (R1 a R17) y penaliza cruces (R14) y concentracion de grupos (R18).
    """

    DEFAULT_DISPONIBILIDAD = [
        DisponibilidadSalon("Lunes",     4, 1),
        DisponibilidadSalon("Martes",    4, 1),
        DisponibilidadSalon("Miercoles", 3, 1),
        DisponibilidadSalon("Jueves",    2, 1),
        DisponibilidadSalon("Viernes",   2, 1),
    ]

    # Franja restringida (R12 y R13): estas materias SOLO pueden programarse en 18-20
    # y ninguna otra materia puede usar esa franja (HC-10 del notebook).
    FRANJA_RESTRINGIDA = "18-20"
    # Cada item es una lista de ALIAS de una misma materia. Se comparan sin tildes,
    # mayusculas, espacios ni guiones (ver _buscar_materias), asi que da igual si el
    # catalogo escribe 'Disciplina 4' o 'DISCIPLINAS 4'. Antes la comparacion era
    # EXACTA (distinguia mayusculas), y las materias que no coincidian letra por letra
    # quedaban bloqueadas de 18-20 sin aviso.
    MATERIAS_18_20_ALIAS = [
        ["Ciberseguridad"],
        ["Disciplina 4", "Disciplinas 4"],
        ["Taller de Habilidades Gerenciales"],
        ["Taller de Habilidades Profesionales"],
    ]
    # Se conserva por compatibilidad; ya no se usa para comparar (usar self.materias_18_20).
    MATERIAS_PERMITIDAS_18_20 = [a for alias in MATERIAS_18_20_ALIAS for a in alias]

    # Franjas permitidas para materias especificas (restricciones DURAS).
    # nombre de la restriccion -> (materias, franjas permitidas)
    # Los nombres se comparan sin tildes, mayusculas, espacios ni guiones, y se
    # aceptan nombres que TERMINEN igual si son unicos ('Defi 1' -> 'Disciplina Defi 1').
    # Si una materia aparece en varias, sus franjas se intersectan.
    RESTRICCIONES_FRANJA = {
        # HC-15: solo en la manana (7:00 - 13:00)
        "solo_manana": (
            ["Calculo 1", "Matematicas Discretas", "Calculo 2", "Algebra Lineal",
             "Probabilidad", "Optimizacion"],
            FRANJAS_MANANA,
        ),
        # HC-17: Disciplina 1, 2 y 3 solo en la manana
        "disciplinas_1_a_3_manana": (
            ["Disciplina 1", "Disciplina 2", "Disciplina 3"],
            FRANJAS_MANANA,
        ),
        # HC-19: Pensamiento Critico 2 solo 14-16
        "pensamiento_critico_2_14_16": (
            ["Pensamiento Critico 2"],
            ["14-16"],
        ),
        # HC-20: Visualizacion 1 y 2 en 14-16 y 16-18
        "visualizacion_14_a_18": (
            ["Visualizacion 1", "Visualizacion 2"],
            ["14-16", "16-18"],
        ),
        # HC-21: Metodos Numericos en 14-16 y 16-18 (ya no va en la manana)
        "metodos_numericos_14_a_18": (
            ["Metodos Numericos"],
            ["14-16", "16-18"],
        ),
    }

    # HC-16 y HC-18: dias especificos por materia (DURAS). Sobrescriben el patron de
    # dias segun sesiones/semana, por lo que R6 y R7 se aplican sin cambios.
    DIAS_LMV = ["Lunes", "Miercoles", "Viernes"]
    DIAS_ESPECIFICOS = {
        "Emprendimiento": ["Lunes", "Miercoles", "Viernes"],   # HC-16: 1 sesion, L/M/V
        "Ciberseguridad": ["Lunes", "Miercoles"],              # HC-18: 2 sesiones, L/M
    }

    MODOS_HC14 = ("binario", "fraccion", "ninguno")

    def __init__(
        self,
        df_proyecciones: pd.DataFrame,
        disponibilidad: Optional[list] = None,
        penalizacion: int = 10,
        penalizacion_cruce: float = 1,
        penalizacion_dispersion: float = 0.5,
        holgura_k: int = 0,
        modo_hc14: str = "fraccion",
    ):
        if modo_hc14 not in self.MODOS_HC14:
            raise ValueError(f"modo_hc14 debe ser uno de {self.MODOS_HC14}, se recibio '{modo_hc14}'")

        self.df                 = df_proyecciones
        self.disponibilidad     = disponibilidad or self.DEFAULT_DISPONIBILIDAD
        self.penalizacion       = penalizacion
        # Penaliza (sin prohibir) que dos materias del mismo semestre queden
        # en el mismo dia-hora, para que los estudiantes de ese semestre
        # puedan cursar ambas. Se deja como penalizacion, no como restriccion
        # dura, porque con la capacidad de salones fija a veces es imposible
        # separar del todo a TODAS las materias de un semestre.
        self.penalizacion_cruce = penalizacion_cruce
        # SC-1: penaliza concentrar grupos de una misma materia en la misma
        # (dia, franja). 0 = sin efecto; debe ser mucho menor que `penalizacion`.
        self.penalizacion_dispersion = penalizacion_dispersion
        self.holgura_k               = holgura_k
        # HC-14: "binario" (original), "fraccion" (cruce total por fraccion de
        # grupos, sin binarias extra) o "ninguno" (sin control de cruces).
        self.modo_hc14               = modo_hc14
        self.model: Optional[ConcreteModel] = None
        self._preprocess()

    # ------------------------------------------------------------------
    # Preprocesamiento
    # ------------------------------------------------------------------

    def _preprocess(self):
        self.slots_teorico = {d.dia: d.slots_teorico for d in self.disponibilidad}
        self.slots_computo = {d.dia: d.slots_computo for d in self.disponibilidad}

        self.materias           = self.df["nombre_materia"].tolist()
        self.grupos_por_materia = {}
        self.sesiones_materia   = {}
        self.sesiones_computo_m = {}
        self.sesiones_teorico_m = {}
        self.tipo_sesion        = {}

        for _, row in self.df.iterrows():
            m  = row["nombre_materia"]
            # CORRECCION: ng se estaba usando sin haber sido definida antes.
            # Se calcula aqui primero y se reutiliza abajo.
            ng = int(row["No_grupos"])
            ns = int(row["numero_sesiones"]) // ng
            nc = int(row["Cantidad_sesiones_computo"]) // ng

            self.grupos_por_materia[m] = list(range(ng))
            self.sesiones_materia[m]   = ns
            self.sesiones_computo_m[m] = nc
            self.sesiones_teorico_m[m] = ns - nc

            if nc == ns:  self.tipo_sesion[m] = "computo"
            elif nc == 0: self.tipo_sesion[m] = "teorico"
            else:         self.tipo_sesion[m] = "mixta"

        self.MG      = [(m, g) for m in self.materias for g in self.grupos_por_materia[m]]
        self.MG_teo  = [(m, g) for (m, g) in self.MG if self.sesiones_teorico_m[m] > 0]
        self.MG_comp = [(m, g) for (m, g) in self.MG if self.sesiones_computo_m[m] > 0]
        # Patron de dias segun sesiones/semana:
        #   3 sesiones -> Lunes, Miercoles, Viernes
        #   2 sesiones -> Martes, Jueves
        #   1 sesion   -> Martes, Jueves TAMBIEN, EXCEPTO si la materia esta
        #                 en MATERIAS_PERMITIDAS_18_20 (esas si pueden ir
        #                 cualquier dia de la semana)
        #   otro caso  -> cualquier dia (4+ sesiones, sin patron definido)
        # Nombres del catalogo que no se encontraron en el dataset (no detienen el modelo)
        self.avisos = []

        # R12/R13: materias exclusivas de 18-20, con los nombres EXACTOS del dataset.
        self.materias_18_20 = []
        for alias in self.MATERIAS_18_20_ALIAS:
            for m in self._buscar_materias(alias, "franja_18_20", avisar=False):
                if m not in self.materias_18_20:
                    self.materias_18_20.append(m)
        if len(self.materias_18_20) < len(self.MATERIAS_18_20_ALIAS):
            faltan = [a[0] for a in self.MATERIAS_18_20_ALIAS if not self._buscar_materias(a, "franja_18_20", avisar=False)]
            self.avisos.append(f"(franja_18_20) no se encontraron en el dataset: {faltan}")

        def _dias_permitidos(m: str, ns: int) -> list:
            if ns == 3:
                return ["Lunes", "Miercoles", "Viernes"]
            if ns == 2:
                return ["Martes", "Jueves"]
            if ns == 1:
                if m in self.materias_18_20:
                    return DIAS
                return ["Martes", "Jueves"]
            return DIAS

        self.dias_permitidos = {
            m: _dias_permitidos(m, self.sesiones_materia[m]) for m in self.materias
        }

        # HC-16 y HC-18: se sobrescriben los dias permitidos ANTES de construir las
        # restricciones 6 y 7, que se arman a partir de este diccionario.
        self.dias_especificos = {}
        for nombre, dias in self.DIAS_ESPECIFICOS.items():
            for m in self._buscar_materias([nombre], "dias_especificos"):
                self.dias_especificos[m] = list(dias)
                self.dias_permitidos[m] = list(dias)

        # HC-15, HC-17, HC-19, HC-20, HC-21: franjas permitidas por materia.
        # franjas_permitidas lo usa tambien SC-1 para el reparto ideal de grupos.
        self.restricciones_franja = {}
        self.franjas_permitidas   = {}
        for nombre, (nombres, franjas_ok) in self.RESTRICCIONES_FRANJA.items():
            encontradas = self._buscar_materias(nombres, nombre)
            self.restricciones_franja[nombre] = (encontradas, list(franjas_ok))
            for m in encontradas:
                previas = self.franjas_permitidas.get(m, list(HORAS))
                self.franjas_permitidas[m] = [t for t in previas if t in franjas_ok]

        for m in self.materias_18_20:
            self.franjas_permitidas[m] = [self.FRANJA_RESTRINGIDA]

        # Materias agrupadas por semestre (columna opcional "semestre" en
        # df_proyecciones, ej. propagada desde dataset_demanda_materias.xlsx).
        # Solo interesan los semestres con 2+ materias: uno con una sola
        # materia no puede tener cruces.
        self.materias_por_semestre = {}
        if "semestre" in self.df.columns:
            semestre_de_materia = dict(zip(self.df["nombre_materia"], self.df["semestre"]))
            for m, s in semestre_de_materia.items():
                if pd.isna(s):
                    continue
                self.materias_por_semestre.setdefault(s, []).append(m)
            self.materias_por_semestre = {
                s: ms for s, ms in self.materias_por_semestre.items() if len(ms) > 1
            }

    def _buscar_materias(self, nombres: list, etiqueta: str, avisar: bool = True) -> list:
        """Traduce nombres del catalogo a los nombres exactos del dataset.
        Acepta variantes de escritura y nombres que TERMINEN igual si son unicos."""
        por_clave   = {_clave(m): m for m in self.materias}
        encontradas = []
        for n in nombres:
            clave = _clave(n)
            m = por_clave.get(clave)
            if m is None:
                candidatas = [v for k, v in por_clave.items() if k.endswith(clave)]
                m = candidatas[0] if len(candidatas) == 1 else None
            if m is None:
                if not avisar:
                    continue
                sug = difflib.get_close_matches(n, self.materias, n=3, cutoff=0.5)
                self.avisos.append(f"({etiqueta}) '{n}' no esta en el dataset -- se ignora. Parecidas: {sug}")
            elif m not in encontradas:
                encontradas.append(m)
        return encontradas

    def franjas_posibles(self, m: str) -> list:
        """Franjas donde la materia m puede programarse (R12, R13, R15)."""
        if m in self.materias_18_20:
            return [self.FRANJA_RESTRINGIDA]
        fr = list(self.franjas_permitidas.get(m, HORAS))
        return [t for t in fr if t != self.FRANJA_RESTRINGIDA]

    # ------------------------------------------------------------------
    # Validacion
    # ------------------------------------------------------------------

    def validate(self) -> list:
        errores = []
        for _, row in self.df.iterrows():
            m  = row["nombre_materia"]
            ns = int(row["numero_sesiones"])
            nc = int(row["Cantidad_sesiones_computo"])
            ng = int(row["No_grupos"])
            if nc > ns:
                errores.append(f"{m}: Cantidad_sesiones_computo ({nc}) > numero_sesiones ({ns})")
            if ng <= 0:
                errores.append(f"{m}: No_grupos debe ser > 0, tiene ({ng})")
        return errores

    # ------------------------------------------------------------------
    # Construccion del modelo
    # ------------------------------------------------------------------

    def build(self) -> ConcreteModel:
        ctx   = self
        model = ConcreteModel()

        model.MG = Set(initialize=self.MG, dimen=2)
        model.D  = Set(initialize=DIAS)
        model.T  = Set(initialize=HORAS)

        model.x_t          = Var(model.MG, model.D, model.T, domain=Binary)
        model.x_c          = Var(model.MG, model.D, model.T, domain=Binary)
        model.z            = Var(model.MG, model.T, domain=Binary)
        model.holgura_teo  = Var(model.MG, domain=NonNegativeReals)
        model.holgura_comp = Var(model.MG, domain=NonNegativeReals)

        # 1. Sesiones teoricas requeridas (+ holgura para suavizar)
        def ses_teo_rule(mdl, m, g):
            return (
                sum(mdl.x_t[(m, g), d, t] for d in mdl.D for t in mdl.T)
                + mdl.holgura_teo[(m, g)]
                == ctx.sesiones_teorico_m[m]
            )
        model.ses_teo = Constraint(model.MG, rule=ses_teo_rule)

        # 2. Sesiones de computo requeridas (+ holgura)
        def ses_comp_rule(mdl, m, g):
            return (
                sum(mdl.x_c[(m, g), d, t] for d in mdl.D for t in mdl.T)
                + mdl.holgura_comp[(m, g)]
                == ctx.sesiones_computo_m[m]
            )
        model.ses_comp = Constraint(model.MG, rule=ses_comp_rule)

        # 3. Capacidad de salones teoricos por dia-hora
        def cap_teo_rule(mdl, d, t):
            return (
                sum(mdl.x_t[(m, g), d, t] for (m, g) in ctx.MG_teo)
                <= ctx.slots_teorico[d]
            )
        model.cap_teo = Constraint(model.D, model.T, rule=cap_teo_rule)

        # 4. Capacidad de salas de computo por dia-hora
        def cap_comp_rule(mdl, d, t):
            return (
                sum(mdl.x_c[(m, g), d, t] for (m, g) in ctx.MG_comp)
                <= ctx.slots_computo[d]
            )
        model.cap_comp = Constraint(model.D, model.T, rule=cap_comp_rule)

        # 5. Un grupo maximo una sesion por dia
        def una_clase_dia_rule(mdl, m, g, d):
            return (
                sum(mdl.x_t[(m, g), d, t] for t in mdl.T)
                + sum(mdl.x_c[(m, g), d, t] for t in mdl.T)
            ) <= 1
        model.una_clase_dia = Constraint(model.MG, model.D, rule=una_clase_dia_rule)

        # 6. Solo dias permitidos - teorico
        def dias_validos_teo_rule(mdl, m, g, d, t):
            if d not in ctx.dias_permitidos[m]:
                return mdl.x_t[(m, g), d, t] == 0
            return Constraint.Skip
        model.dias_validos_teo = Constraint(
            model.MG, model.D, model.T, rule=dias_validos_teo_rule
        )

        # 7. Solo dias permitidos - computo
        def dias_validos_comp_rule(mdl, m, g, d, t):
            if d not in ctx.dias_permitidos[m]:
                return mdl.x_c[(m, g), d, t] == 0
            return Constraint.Skip
        model.dias_validos_comp = Constraint(
            model.MG, model.D, model.T, rule=dias_validos_comp_rule
        )

        # 8. Materias solo teoricas no usan sala de computo
        def solo_teo_rule(mdl, m, g, d, t):
            if ctx.tipo_sesion[m] == "teorico":
                return mdl.x_c[(m, g), d, t] == 0
            return Constraint.Skip
        model.solo_teo = Constraint(model.MG, model.D, model.T, rule=solo_teo_rule)

        # 9. Materias solo de computo no usan salon teorico
        def solo_comp_rule(mdl, m, g, d, t):
            if ctx.tipo_sesion[m] == "computo":
                return mdl.x_t[(m, g), d, t] == 0
            return Constraint.Skip
        model.solo_comp = Constraint(model.MG, model.D, model.T, rule=solo_comp_rule)

        # 10. (R12) Franja 18-20 restringida a materias especificas
        def franja_18_20_rule(mdl, m, g, d):
            if m not in ctx.materias_18_20:
                return (
                    mdl.x_t[(m, g), d, ctx.FRANJA_RESTRINGIDA]
                    + mdl.x_c[(m, g), d, ctx.FRANJA_RESTRINGIDA]
                ) == 0
            return Constraint.Skip
        model.franja_18_20 = Constraint(model.MG, model.D, rule=franja_18_20_rule)

        # (R13) Las materias exclusivas de 18-20 SOLO pueden programarse en esa franja.
        # Antes faltaba esta mitad de la regla: estas materias podian quedar de dia.
        def exclusivas_18_20_rule(mdl, m, g, d, t):
            if m in ctx.materias_18_20 and t != ctx.FRANJA_RESTRINGIDA:
                return mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] == 0
            return Constraint.Skip
        model.exclusivas_18_20 = Constraint(
            model.MG, model.D, model.T, rule=exclusivas_18_20_rule
        )

        # 11. Cada grupo elige exactamente una franja fija (solo si sesiones_materia > 1)
        def una_franja_rule(mdl, m, g):
            if ctx.sesiones_materia[m] > 1:
                return sum(mdl.z[(m, g), t] for t in mdl.T) == 1
            return Constraint.Skip
        model.una_franja = Constraint(model.MG, rule=una_franja_rule)

        # 12. Todas las sesiones de un grupo van en su franja fija (con holgura).
        # CORRECCION: antes era una igualdad ("=="), que exigia el 100% de las
        # sesiones exactas en la franja elegida y, si los salones no
        # alcanzaban, no habia ningun z factible -> el modelo completo se
        # volvia infeasible (por eso estaba desactivada). Con "<=" el modelo
        # puede asignar menos sesiones en la franja elegida y dejar el resto
        # como holgura_teo/holgura_comp (restricciones 1-2), en vez de
        # tumbar todo el problema. Por eso ya se puede dejar ACTIVA.
        def franja_fija_rule(mdl, m, g, t):
            if ctx.sesiones_materia[m] > 1:
                return (
                    sum(mdl.x_t[(m, g), d, t] for d in ctx.dias_permitidos[m])
                    + sum(mdl.x_c[(m, g), d, t] for d in ctx.dias_permitidos[m])
                ) <= ctx.sesiones_materia[m] * mdl.z[(m, g), t]
            return Constraint.Skip
        model.franja_fija = Constraint(model.MG, model.T, rule=franja_fija_rule)

        # 13. (R17) En la franja 18-20 solo puede haber UNA MATERIA por dia, pero
        # TODOS sus grupos pueden estar ahi.
        #
        # CORRECCION: antes esta restriccion contaba GRUPOS (<= 1), o sea una
        # sola clase a las 18-20 en todo el dia. Con eso el modelo no puede
        # reproducir la realidad: los 5 tracks de DISCIPLINAS 4 van juntos a
        # las 18-20 martes y jueves. Al unificarlos en una sola materia con 5
        # grupos, lo correcto es limitar cuantas MATERIAS distintas ocupan la
        # franja. u[m,d] marca si la materia m usa la franja ese dia.
        materias_18_20 = list(ctx.materias_18_20)
        model.M18 = Set(initialize=materias_18_20)
        model.u_18_20 = Var(model.M18, model.D, domain=Binary)

        def link_18_20_rule(mdl, m, g, d):
            if m in ctx.materias_18_20:
                return (
                    mdl.x_t[(m, g), d, ctx.FRANJA_RESTRINGIDA]
                    + mdl.x_c[(m, g), d, ctx.FRANJA_RESTRINGIDA]
                ) <= mdl.u_18_20[m, d]
            return Constraint.Skip
        model.link_18_20 = Constraint(model.MG, model.D, rule=link_18_20_rule)

        def una_materia_18_20_rule(mdl, d):
            if not materias_18_20:
                return Constraint.Skip
            return sum(mdl.u_18_20[m, d] for m in mdl.M18) <= 1
        model.una_materia_18_20 = Constraint(model.D, rule=una_materia_18_20_rule)

        # 14. Cruces entre materias del mismo semestre (penalizado, no duro).
        # ocupa[m,d,t] = 1 si la materia m tiene AL MENOS un grupo con sesion
        # (teorica o de computo) en ese dia-hora. cruce_sem[s,d,t] mide
        # cuantas materias de un mismo semestre se pasan de 1 coincidiendo
        # en el mismo dia-hora: si 3 materias de "cuarto semestre" caen en
        # Lunes 7-9, cruce_sem = 2 (la primera es "gratis", las siguientes 2
        # son cruce). Se penaliza en el objetivo para que el solver las
        # separe cuando la capacidad de salones lo permita.
        # Lo anterior es el modo "binario"; ver `modo_hc14` para "fraccion" y "ninguno".
        materias_con_semestre = sorted({
            m for ms in ctx.materias_por_semestre.values() for m in ms
        })
        model.SEM   = Set(initialize=list(ctx.materias_por_semestre.keys()))
        model.M_sem = Set(initialize=materias_con_semestre)

        # En todos los modos existe cruce_sem (en "ninguno" no tiene restricciones y vale 0)
        model.cruce_sem = Var(model.SEM, model.D, model.T, domain=NonNegativeReals)

        if ctx.modo_hc14 == "binario":
            model.ocupa = Var(model.M_sem, model.D, model.T, domain=Binary)

            def link_ocupa_rule(mdl, m, d, t):
                return (
                    sum(mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] for g in ctx.grupos_por_materia[m])
                    <= len(ctx.grupos_por_materia[m]) * mdl.ocupa[m, d, t]
                )
            model.link_ocupa = Constraint(model.M_sem, model.D, model.T, rule=link_ocupa_rule)

            def cruce_sem_rule(mdl, s, d, t):
                materias_s = ctx.materias_por_semestre[s]
                return sum(mdl.ocupa[m, d, t] for m in materias_s) - 1 <= mdl.cruce_sem[s, d, t]
            model.cruce_sem_con = Constraint(model.SEM, model.D, model.T, rule=cruce_sem_rule)

        elif ctx.modo_hc14 == "fraccion":
            # Cada materia aporta la FRACCION de sus grupos que cae en (d,t); hay
            # cruce solo si la suma de fracciones supera 1 (cruce "total").
            def cruce_sem_rule(mdl, s, d, t):
                return (
                    sum(
                        sum(mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] for g in ctx.grupos_por_materia[m])
                        / len(ctx.grupos_por_materia[m])
                        for m in ctx.materias_por_semestre[s]
                    ) - 1 <= mdl.cruce_sem[s, d, t]
                )
            model.cruce_sem_con = Constraint(model.SEM, model.D, model.T, rule=cruce_sem_rule)

        # 15 (HC-15, 17, 19, 20, 21). Franjas permitidas para materias especificas (DURAS):
        # fuera de las franjas de cada restriccion, x = 0 para todos sus grupos.
        for nombre, (materias_r, franjas_ok) in ctx.restricciones_franja.items():
            conjunto = Set(initialize=[(m, g) for (m, g) in ctx.MG if m in materias_r], dimen=2)
            model.add_component(f"MG_{nombre}", conjunto)

            def franjas_rule(mdl, m, g, d, t, franjas_ok=franjas_ok):
                if t not in franjas_ok:
                    return mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] == 0
                return Constraint.Skip
            model.add_component(
                nombre, Constraint(conjunto, model.D, model.T, rule=franjas_rule)
            )

        # 16 (HC-16 y HC-18). Materias con dias especificos (DIAS_ESPECIFICOS).
        # Ya quedan cubiertas por la 6 y la 7 (dias_permitidos se sobrescribe en
        # _preprocess), pero se deja explicita.
        model.MG_dias_esp = Set(
            initialize=[(m, g) for (m, g) in ctx.MG if m in ctx.dias_especificos], dimen=2
        )

        def dias_especificos_rule(mdl, m, g, d, t):
            if d not in ctx.dias_especificos[m]:
                return mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] == 0
            return Constraint.Skip
        model.solo_dias_especificos = Constraint(
            model.MG_dias_esp, model.D, model.T, rule=dias_especificos_rule
        )

        # SC-1 (blanda). Distribuir los grupos de una misma materia entre franjas.
        #   K_m           = ceil(grupos / franjas posibles) + holgura_k
        #   exceso[m,d,t] >= (grupos de m con sesion en (d,t)) - K_m
        # Se cuenta con x_t / x_c (no con z) porque z es solo una cota superior
        # de la 12 y podria quedar en 1 sin sesiones asignadas.
        self.k_grupos = {
            m: max(1, math.ceil(
                len(ctx.grupos_por_materia[m]) / max(1, len(ctx.franjas_posibles(m)))
            ) + ctx.holgura_k)
            for m in ctx.materias
        }
        materias_dispersion = [
            m for m in ctx.materias if len(ctx.grupos_por_materia[m]) > self.k_grupos[m]
        ]
        model.M_disp = Set(initialize=materias_dispersion)
        model.exceso = Var(model.M_disp, model.D, model.T, domain=NonNegativeReals)

        def exceso_rule(mdl, m, d, t):
            return (
                mdl.exceso[m, d, t]
                >= sum(mdl.x_t[(m, g), d, t] + mdl.x_c[(m, g), d, t] for g in ctx.grupos_por_materia[m])
                - ctx.k_grupos[m]
            )
        model.exceso_con = Constraint(model.M_disp, model.D, model.T, rule=exceso_rule)

        # Objetivo: maximizar sesiones asignadas - penalizacion por holgura
        # - penalizacion por cruces entre materias del mismo semestre
        # - penalizacion por concentrar grupos de una materia en la misma franja (SC-1)
        model.obj = Objective(
            expr=(
                sum(
                    model.x_t[(m, g), d, t] + model.x_c[(m, g), d, t]
                    for (m, g) in model.MG for d in model.D for t in model.T
                )
                - self.penalizacion * sum(
                    model.holgura_teo[(m, g)] + model.holgura_comp[(m, g)]
                    for (m, g) in model.MG
                )
                - self.penalizacion_cruce * sum(
                    model.cruce_sem[s, d, t]
                    for s in model.SEM for d in model.D for t in model.T
                )
                - self.penalizacion_dispersion * sum(
                    model.exceso[m, d, t]
                    for m in model.M_disp for d in model.D for t in model.T
                )
            ),
            sense=maximize,
        )

        self.model = model
        return model

    # ------------------------------------------------------------------
    # Resolucion
    # ------------------------------------------------------------------

    def solve(self, solver_name: str = "appsi_highs", tee: bool = False,
              time_limit: Optional[float] = None, mip_rel_gap: Optional[float] = None):
        """Resuelve el modelo. Solver por defecto: HiGHS ('appsi_highs'); si no esta
        instalado se usa GLPK. `time_limit` (segundos) y `mip_rel_gap` son opcionales."""
        if self.model is None:
            self.build()
        solver = SolverFactory(solver_name)
        if solver_name != "glpk" and not solver.available(exception_flag=False):
            self.avisos.append(f"El solver '{solver_name}' no esta disponible; se uso GLPK.")
            solver_name, solver = "glpk", SolverFactory("glpk")

        opciones = {}
        if solver_name == "glpk":
            if time_limit is not None:  opciones["tmlim"] = int(time_limit)
            if mip_rel_gap is not None: opciones["mipgap"] = mip_rel_gap
        else:
            if time_limit is not None:  opciones["time_limit"] = float(time_limit)
            if mip_rel_gap is not None: opciones["mip_rel_gap"] = mip_rel_gap
        return solver.solve(self.model, tee=tee, options=opciones) if opciones else solver.solve(self.model, tee=tee)

    @staticmethod
    def is_optimal(results) -> bool:
        return (
            results.solver.status == SolverStatus.ok
            and results.solver.termination_condition == TerminationCondition.optimal
        )

    # ------------------------------------------------------------------
    # Extraccion de resultados
    # ------------------------------------------------------------------

    def get_results(self) -> ResultadoScheduler:
        model       = self.model
        orden_dias  = {d: i for i, d in enumerate(DIAS)}
        orden_horas = {h: i for i, h in enumerate(HORAS)}

        filas_horario = []
        for (m, g) in model.MG:
            for d in model.D:
                for t in model.T:
                    try:
                        if value(model.x_t[(m, g), d, t]) >= 0.5:
                            filas_horario.append({
                                "Materia": m, "Grupo": g,
                                "Tipo_Salon": "teorico", "Dia": d, "Hora": t,
                            })
                    except Exception:
                        pass
                    try:
                        if value(model.x_c[(m, g), d, t]) >= 0.5:
                            filas_horario.append({
                                "Materia": m, "Grupo": g,
                                "Tipo_Salon": "computo", "Dia": d, "Hora": t,
                            })
                    except Exception:
                        pass

        horario_df = pd.DataFrame(filas_horario)

        resumen_grupos = []
        for (m, g) in model.MG:
            ht       = round(value(model.holgura_teo[(m, g)]))
            hc       = round(value(model.holgura_comp[(m, g)]))
            completo = ht == 0 and hc == 0

            # CORRECCION: antes este mensaje se construia revisando si cada dia
            # permitido tenia sesion teorica Y sesion de computo por separado.
            # En una materia MIXTA eso siempre da falso positivo: la
            # restriccion 5 permite maximo UNA sesion por grupo por dia, asi
            # que cada dia tiene teorica O computo, nunca ambas, y el
            # complemento nunca queda vacio. Resultado: grupos con
            # "Logro asignacion completa = Si" mostraban texto en "Que falta".
            #
            # Ahora el mensaje sale de la MISMA holgura que decide `completo`,
            # asi que las dos columnas no se pueden contradecir: si completo
            # es "Si" entonces ht == hc == 0, no se agrega ningun mensaje y
            # "Que falta" queda en "-".
            mensajes = []
            if ht > 0:
                mensajes.append(f"Faltan {ht} sesion(es) teorica(s)")
            if hc > 0:
                mensajes.append(f"Faltan {hc} sesion(es) de computo")

            resumen_grupos.append({
                "Materia":                   m,
                "Grupo":                     g,
                "Ses. requeridas":           self.sesiones_materia[m],
                "Ses. asignadas":            self.sesiones_materia[m] - ht - hc,
                "Ses. teo faltantes":        ht,
                "Ses. comp faltantes":       hc,
                "Logro asignacion completa": "Si" if completo else "No",
                "Que falta":                 " | ".join(mensajes) if mensajes else "-",
            })

        resumen_df = pd.DataFrame(resumen_grupos)

        if not horario_df.empty:
            horario_df["ord_dia"]  = horario_df["Dia"].map(orden_dias)
            horario_df["ord_hora"] = horario_df["Hora"].map(orden_horas)
            horario_df = (
                horario_df
                .sort_values(["Materia", "Grupo", "ord_dia", "ord_hora"])
                .drop(columns=["ord_dia", "ord_hora"])
                .merge(
                    resumen_df[["Materia", "Grupo", "Logro asignacion completa", "Que falta"]],
                    on=["Materia", "Grupo"],
                    how="left",
                )
            )
            horario_df = horario_df[[
                "Materia", "Grupo", "Tipo_Salon", "Dia", "Hora",
                "Logro asignacion completa", "Que falta",
            ]]

        total     = len(resumen_df)
        completos = int(resumen_df["Logro asignacion completa"].str.contains("Si").sum())

        return ResultadoScheduler(
            horario=horario_df,
            resumen=resumen_df,
            total_grupos=total,
            completos=completos,
            incompletos=total - completos,
        )
