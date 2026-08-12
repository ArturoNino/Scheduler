# Entry point for the math-scheduler backend API

from pathlib import Path

import pandas as pd

from model.scheduler import SchedulerModel


# Catalogo de materias (nombre_materia, numero_sesiones, Cantidad_sesiones_computo, No_grupos)
RUTA_CATALOGO = r"D:\UNIVERSIDAD\PROYECTO\codigo_git_hub\codigos_prueba\dataset_demanda_materias.xlsx"

# Excel de salida con los resultados (se crea junto a este archivo)
RUTA_SALIDA_EXCEL = Path(__file__).resolve().parent / "resultado_horario.xlsx"


def cargar_df_proyecciones(ruta: str = RUTA_CATALOGO) -> pd.DataFrame:
    return pd.read_excel(ruta)


def ejecutar_modelo(df_proyecciones: pd.DataFrame) -> SchedulerModel:
    """Construye, valida y resuelve el modelo. Lanza una excepcion si no hay solucion optima."""
    sched = SchedulerModel(df_proyecciones)

    errores = sched.validate()
    if errores:
        raise ValueError("Datos de entrada invalidos:\n" + "\n".join(errores))

    sched.build()
    results = sched.solve()

    if not SchedulerModel.is_optimal(results):
        raise RuntimeError(
            "El solver no encontro una solucion optima. "
            f"Estado={results.solver.status}, Condicion={results.solver.termination_condition}"
        )

    return sched


def imprimir_resultados(resultado) -> None:
    print("=" * 90)
    print("HORARIO GENERADO")
    print("=" * 90)
    if resultado.horario.empty:
        print("No se genero ninguna asignacion.")
    else:
        print(resultado.horario.to_string(index=False))

    incompletos_df = resultado.resumen[resultado.resumen["Logro asignacion completa"] == "No"]

    print("\n" + "=" * 90)
    print("MATERIAS INCOMPLETAS O SIN ASIGNAR")
    print("=" * 90)
    if incompletos_df.empty:
        print("Todas las materias quedaron asignadas completamente.")
    else:
        print(
            incompletos_df[
                ["Materia", "Grupo", "Ses. requeridas", "Ses. asignadas", "Que falta"]
            ].to_string(index=False)
        )

    print(f"\nGrupos totales: {resultado.total_grupos}  "
          f"Completos: {resultado.completos}  "
          f"Incompletos: {resultado.incompletos}")


def guardar_excel(resultado, ruta_salida: Path = RUTA_SALIDA_EXCEL) -> None:
    """Guarda dos hojas: 'Programacion' (horario completo) y
    'Incompletas o sin asignar' (materias que no lograron asignacion completa)."""
    incompletos_df = resultado.resumen[resultado.resumen["Logro asignacion completa"] == "No"]

    with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
        resultado.horario.to_excel(writer, sheet_name="Programacion", index=False)
        incompletos_df.to_excel(writer, sheet_name="Incompletas o sin asignar", index=False)

    print(f"\nResultados guardados en: {ruta_salida}")


def main():
    df_proyecciones = cargar_df_proyecciones()
    sched = ejecutar_modelo(df_proyecciones)
    resultado = sched.get_results()

    imprimir_resultados(resultado)
    guardar_excel(resultado)


if __name__ == "__main__":
    main()
