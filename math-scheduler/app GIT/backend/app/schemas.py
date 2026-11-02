from __future__ import annotations

from typing import Literal

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
    activar_cruce_semestre: bool = False
    penalizacion_cruce: float = 5
    # Formulación del cruce entre materias del mismo semestre (SC12).
    modo_cruce_semestre: Literal["binario", "fraccion", "ninguno"] = "binario"
    # Correcciones de los tutores: HC15-HC19 (franjas por materia) y HC16 (Emprendimiento L-M-V).
    activar_restricciones_materia: bool = True
    # SC13: dispersión de grupos de una misma materia (0 = desactivada).
    penalizacion_dispersion: float = Field(default=0.5, ge=0)
    holgura_k: int = Field(default=0, ge=0)
    tiempo_limite_segundos: float = Field(default=120, gt=0)


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
    # Semestre del pénsum (None si la materia no tiene semestre asignado);
    # lo usa el frontend para el filtro de visualización por semestre.
    semestre: int | None = None
    tipo_salon: str
    dia: str
    hora: str


class ResumenItem(BaseModel):
    materia: str
    grupo: int
    semestre: int | None = None
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
    # Notas del modelo (p. ej. reglas por nombre que no se encontraron en el dataset).
    avisos: list[str] = []
    tiempo_segundos: float
    horario: list[HorarioItem] = []
    resumen: list[ResumenItem] = []
    uso_salones: list[UsoSalonItem] = []
    kpis: dict = {}
