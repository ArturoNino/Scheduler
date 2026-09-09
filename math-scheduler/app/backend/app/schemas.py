from __future__ import annotations

from pydantic import BaseModel, Field


class DisponibilidadDia(BaseModel):
    teorico: int = Field(ge=0)
    computo: int = Field(ge=0)


class ConfigSolver(BaseModel):
    dataset_id: str
    dias: list[str]
    horas: list[str]
    disponibilidad: dict[str, DisponibilidadDia]
    penalizacion: float = 10
    activar_franja_fija: bool = True
    activar_franja_18_20: bool = True


class DatasetPreview(BaseModel):
    dataset_id: str
    filas: int
    columnas: list[str]
    preview: list[dict]
    errores: list[str]
    dias_default: list[str]
    horas_default: list[str]
    disponibilidad_default: dict[str, DisponibilidadDia]


class ProjectionResponse(BaseModel):
    dataset_id: str
    filas: int
    columnas_dataset: list[str]
    dataset_solver: list[dict]
    columnas_detalle: list[str]
    proyeccion_detallada: list[dict]
    materias_sin_catalogo: list[str]
    advertencias_prerrequisitos: list[str]
    materias_core: list[str]
    cap_core_usado: int
    cap_otras_usado: int
    dias_default: list[str]
    horas_default: list[str]
    disponibilidad_default: dict[str, DisponibilidadDia]


class HorarioItem(BaseModel):
    materia: str
    grupo: int
    tipo_salon: str
    dia: str
    hora: str


class ResumenItem(BaseModel):
    materia: str
    grupo: int
    sesiones_requeridas: int
    sesiones_asignadas: int
    asignacion_completa: bool
    diagnostico: str | None = None
    sesiones_teo_asignadas: list[str]
    sesiones_comp_asignadas: list[str]


class UsoSalonItem(BaseModel):
    dia: str
    hora: str
    teorico_usados: int
    teorico_disponibles: int
    computo_usados: int
    computo_disponibles: int


class SolverResponse(BaseModel):
    estado: str
    condicion: str
    factible: bool
    mensaje: str | None = None
    tiempo_segundos: float
    horario: list[HorarioItem] = []
    resumen: list[ResumenItem] = []
    uso_salones: list[UsoSalonItem] = []
    kpis: dict = {}
