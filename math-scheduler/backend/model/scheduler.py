from dataclasses import dataclass
from typing import Optional

import pandas as pd
from pyomo.environ import (
    Binary, ConcreteModel, Constraint, NonNegativeReals,
    Objective, Set, SolverFactory, Var, maximize, value,
)
from pyomo.opt import SolverStatus, TerminationCondition


DIAS  = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes"]
HORAS = ["7-9", "9-11", "11-13", "14-16", "16-18"]


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
    ILP para asignacion de horarios academicos (Pyomo + GLPK).
    Maximiza sesiones asignadas respetando capacidad de salones teoricos y de computo.
    """

    DEFAULT_DISPONIBILIDAD = [
        DisponibilidadSalon("Lunes",     4, 1),
        DisponibilidadSalon("Martes",    4, 1),
        DisponibilidadSalon("Miercoles", 3, 1),
        DisponibilidadSalon("Jueves",    2, 1),
        DisponibilidadSalon("Viernes",   2, 1),
    ]

    def __init__(
        self,
        df_proyecciones: pd.DataFrame,
        disponibilidad: Optional[list] = None,
        penalizacion: int = 10,
    ):
        self.df             = df_proyecciones
        self.disponibilidad = disponibilidad or self.DEFAULT_DISPONIBILIDAD
        self.penalizacion   = penalizacion
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
            ns = int(row["numero_sesiones"])
            nc = int(row["Cantidad_sesiones_computo"])

            self.grupos_por_materia[m] = list(range(int(row["No_grupos"])))
            self.sesiones_materia[m]   = ns
            self.sesiones_computo_m[m] = nc
            self.sesiones_teorico_m[m] = ns - nc

            if nc == ns:  self.tipo_sesion[m] = "computo"
            elif nc == 0: self.tipo_sesion[m] = "teorico"
            else:         self.tipo_sesion[m] = "mixta"

        self.MG      = [(m, g) for m in self.materias for g in self.grupos_por_materia[m]]
        self.MG_teo  = [(m, g) for (m, g) in self.MG if self.sesiones_teorico_m[m] > 0]
        self.MG_comp = [(m, g) for (m, g) in self.MG if self.sesiones_computo_m[m] > 0]
        self.dias_permitidos = {
            m: ["Lunes", "Miercoles", "Viernes"] if self.sesiones_materia[m] == 3
               else ["Martes", "Jueves"]
            for m in self.materias
        }

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

        # 10-11. Franja horaria fija - desactivadas: generan infeasibility en datos actuales
        def una_franja_rule(mdl, m, g):
            if ctx.sesiones_materia[m] > 1:
                return sum(mdl.z[(m, g), t] for t in mdl.T) == 1
            return Constraint.Skip
        model.una_franja = Constraint(model.MG, rule=una_franja_rule)

        def franja_fija_rule(mdl, m, g, t):
            if ctx.sesiones_materia[m] > 1:
                return (
                    sum(mdl.x_t[(m, g), d, t] for d in ctx.dias_permitidos[m])
                    + sum(mdl.x_c[(m, g), d, t] for d in ctx.dias_permitidos[m])
                ) == ctx.sesiones_materia[m] * mdl.z[(m, g), t]
            return Constraint.Skip
        model.franja_fija = Constraint(model.MG, model.T, rule=franja_fija_rule)

        model.una_franja.deactivate()
        model.franja_fija.deactivate()

        # Objetivo: maximizar sesiones asignadas - penalizacion por holgura
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
            ),
            sense=maximize,
        )

        self.model = model
        return model

    # ------------------------------------------------------------------
    # Resolucion
    # ------------------------------------------------------------------

    def solve(self, solver_name: str = "glpk", tee: bool = False):
        if self.model is None:
            self.build()
        solver  = SolverFactory(solver_name)
        results = solver.solve(self.model, tee=tee)
        return results

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

            dias_asg_teo  = []
            dias_asg_comp = []
            for d in self.dias_permitidos[m]:
                for t in model.T:
                    try:
                        if value(model.x_t[(m, g), d, t]) >= 0.5:
                            dias_asg_teo.append(d)
                    except Exception:
                        pass
                    try:
                        if value(model.x_c[(m, g), d, t]) >= 0.5:
                            dias_asg_comp.append(d)
                    except Exception:
                        pass

            mensajes = (
                [f"{d}: falto salon teorico"
                 for d in self.dias_permitidos[m]
                 if d not in dias_asg_teo and self.sesiones_teorico_m[m] > 0]
                + [f"{d}: falto sala de computo"
                   for d in self.dias_permitidos[m]
                   if d not in dias_asg_comp and self.sesiones_computo_m[m] > 0]
            )

            resumen_grupos.append({
                "Materia":                   m,
                "Grupo":                     g,
                "Ses. requeridas":           self.sesiones_materia[m],
                "Ses. asignadas":            self.sesiones_materia[m] - ht - hc,
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
