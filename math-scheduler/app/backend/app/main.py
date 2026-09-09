"""
API FastAPI para el proyecto de optimización de horarios.

Endpoints:
  GET  /api/health                -> chequeo de salud + disponibilidad de GLPK
  GET  /api/config/default        -> días/horas/disponibilidad por defecto
  POST /api/dataset/upload        -> sube el .xlsx, valida y lo deja en memoria
  POST /api/solve                 -> corre el solver sobre un dataset ya subido

Cómo correrlo (desde backend/):
  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import io
import uuid

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pyomo.environ import SolverFactory

from app.core.materias import es_codigo_conocido, nombre_materia
from app.core.proyeccion import ProyectorUnificado, generar_dataset_solver_unificado
from app.core.scheduler import (
    COLUMNAS_REQUERIDAS,
    DIAS_DEFAULT,
    DISPONIBILIDAD_DEFAULT,
    HORAS_DEFAULT,
    resolver_horario,
    validar_dataset,
)
from app.schemas import (
    ConfigSolver,
    DatasetPreview,
    ProjectionResponse,
    SolverResponse,
)

app = FastAPI(
    title="Scheduler Optimizer API",
    description="Optimización de asignación de horarios académicos (MILP con Pyomo).",
    version="1.0.0",
)

# En desarrollo, Vite corre por defecto en :5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento en memoria (suficiente para una demo/presentación local).
# Si necesitas persistencia real entre reinicios, cambia esto por un
# archivo temporal o una base de datos ligera (sqlite).
_DATASETS: dict[str, pd.DataFrame] = {}


@app.get("/api/health")
def health():
    glpk_ok = SolverFactory("glpk").available()
    return {"status": "ok", "glpk_disponible": bool(glpk_ok)}


@app.get("/api/config/default")
def config_default():
    return {
        "dias": DIAS_DEFAULT,
        "horas": HORAS_DEFAULT,
        "disponibilidad": DISPONIBILIDAD_DEFAULT,
    }


async def _leer_excel(file: UploadFile) -> pd.DataFrame:
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, f"'{file.filename}' debe ser .xlsx o .xls")
    contenido = await file.read()
    try:
        return pd.read_excel(io.BytesIO(contenido))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"No se pudo leer '{file.filename}': {exc}") from exc


@app.post("/api/proyeccion/generar", response_model=ProjectionResponse)
async def generar_proyeccion(
    archivo: UploadFile = File(
        ...,
        description=(
            "materias, estudiantes_actuales, porcentaje_perdida, "
            "inscritos_nuevos, computo, teoricos, sesiones por grupo"
        ),
    ),
    cap_otras: int = Form(35),
    cap_core: int = Form(20),
    redondeo: str = Form("round"),
):
    """Corre la proyección de matrícula + división de grupos y arma el
    dataset listo para el solver, a partir de UN solo archivo que trae
    la matrícula y las sesiones por grupo en las mismas filas."""
    df_raw = await _leer_excel(archivo)

    try:
        resultado = generar_dataset_solver_unificado(
            df_raw=df_raw,
            cap_otras=cap_otras,
            cap_core=cap_core,
            redondeo=redondeo,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    dataset_solver = resultado["dataset_solver"]
    proyeccion_detallada = resultado["proyeccion_detallada"].copy()
    # Tamaños_grupos es una lista por fila; a texto para que serialice limpio en la tabla.
    if "Tamaños_grupos" in proyeccion_detallada.columns:
        proyeccion_detallada["Tamaños_grupos"] = proyeccion_detallada["Tamaños_grupos"].apply(
            lambda xs: ", ".join(map(str, xs)) if isinstance(xs, list) else xs
        )

    dataset_id = str(uuid.uuid4())
    _DATASETS[dataset_id] = dataset_solver

    return ProjectionResponse(
        dataset_id=dataset_id,
        filas=len(dataset_solver),
        columnas_dataset=dataset_solver.columns.tolist(),
        dataset_solver=dataset_solver.to_dict(orient="records"),
        columnas_detalle=proyeccion_detallada.columns.tolist(),
        proyeccion_detallada=proyeccion_detallada.to_dict(orient="records"),
        materias_sin_catalogo=resultado["materias_sin_catalogo"],
        advertencias_prerrequisitos=resultado["advertencias_prerrequisitos"],
        materias_core=[_mostrar_materia(c) for c in sorted(ProyectorUnificado.MATERIAS_MAX20)],
        cap_core_usado=cap_core,
        cap_otras_usado=cap_otras,
        dias_default=DIAS_DEFAULT,
        horas_default=HORAS_DEFAULT,
        disponibilidad_default=DISPONIBILIDAD_DEFAULT,
    )


@app.post("/api/dataset/upload", response_model=DatasetPreview)
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "El archivo debe ser .xlsx o .xls")

    contenido = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contenido))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"No se pudo leer el archivo: {exc}") from exc

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise HTTPException(
            400,
            f"Faltan columnas requeridas: {', '.join(faltantes)}. "
            f"Columnas encontradas: {', '.join(df.columns.astype(str))}",
        )

    errores = validar_dataset(df)

    dataset_id = str(uuid.uuid4())
    _DATASETS[dataset_id] = df

    return DatasetPreview(
        dataset_id=dataset_id,
        filas=len(df),
        columnas=df.columns.tolist(),
        preview=df.head(10).to_dict(orient="records"),
        errores=errores,
        dias_default=DIAS_DEFAULT,
        horas_default=HORAS_DEFAULT,
        disponibilidad_default=DISPONIBILIDAD_DEFAULT,
    )


def _mostrar_materia(valor: str) -> str:
    """'MA0107' -> 'Cálculo 2 (MA0107)' si el código es conocido; si no
    es un código reconocido (p. ej. viene un nombre en texto libre de
    un dataset viejo subido directo), se muestra tal cual."""
    if es_codigo_conocido(valor):
        return f"{nombre_materia(valor)} ({valor.strip().upper()})"
    return valor


@app.post("/api/solve", response_model=SolverResponse)
def solve(config: ConfigSolver):
    df = _DATASETS.get(config.dataset_id)
    if df is None:
        raise HTTPException(
            404, "dataset_id no encontrado. Vuelve a subir el archivo."
        )

    disponibilidad = {
        dia: {"teorico": d.teorico, "computo": d.computo}
        for dia, d in config.disponibilidad.items()
    }

    resultado = resolver_horario(
        df=df,
        dias=config.dias,
        horas=config.horas,
        disponibilidad=disponibilidad,
        penalizacion=config.penalizacion,
        activar_franja_fija=config.activar_franja_fija,
        activar_franja_18_20=config.activar_franja_18_20,
    )

    horario = [{**h, "materia": _mostrar_materia(h["materia"])} for h in resultado.horario]
    resumen = [{**r, "materia": _mostrar_materia(r["materia"])} for r in resultado.resumen]

    return SolverResponse(
        estado=resultado.estado,
        condicion=resultado.condicion,
        factible=resultado.factible,
        mensaje=resultado.mensaje,
        tiempo_segundos=resultado.tiempo_segundos,
        horario=horario,
        resumen=resumen,
        uso_salones=resultado.uso_salones,
        kpis=resultado.kpis,
    )
