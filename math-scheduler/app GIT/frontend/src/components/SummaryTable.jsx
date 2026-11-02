import { exportarExcel } from "../utils/exportarExcel.js";

/**
 * Resumen por materia-grupo. `resumen` llega YA filtrado (por grupo o por
 * semestre) desde App.jsx. `sufijoArchivo` se agrega al nombre del Excel.
 */
export default function SummaryTable({ resumen, sufijoArchivo = "" }) {
  if (!resumen || resumen.length === 0) {
    return <p className="muted">No hay grupos para mostrar con este filtro.</p>;
  }

  function handleExportar() {
    const columnas = [
      "Materia", "Semestre", "Grupo", "Requeridas", "Asignadas", "Completa", "Diagnóstico",
    ];
    const filas = resumen.map((r) => ({
      Materia: r.materia,
      Semestre: r.semestre ?? "",
      Grupo: r.grupo + 1,
      Requeridas: r.sesiones_requeridas,
      Asignadas: r.sesiones_asignadas,
      Completa: r.asignacion_completa ? "Sí" : "No",
      Diagnóstico: r.diagnostico || "",
    }));
    exportarExcel(`resumen_por_grupo${sufijoArchivo}`, columnas, filas, "Resumen");
  }

  return (
    <div>
      <div className="table-toolbar">
        <button type="button" className="export-excel-btn" onClick={handleExportar}>
          ⬇ Excel
        </button>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Materia</th>
              <th>Semestre</th>
              <th>Grupo</th>
              <th>Requeridas</th>
              <th>Asignadas</th>
              <th>Completa</th>
              <th>Diagnóstico</th>
            </tr>
          </thead>
          <tbody>
            {resumen.map((r, idx) => (
              <tr key={idx} className={r.asignacion_completa ? "" : "fila-incompleta"}>
                <td>{r.materia}</td>
                <td>{r.semestre ?? "—"}</td>
                <td>{r.grupo + 1}</td>
                <td>{r.sesiones_requeridas}</td>
                <td>{r.sesiones_asignadas}</td>
                <td>{r.asignacion_completa ? "Sí" : "No"}</td>
                <td>{r.diagnostico || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
