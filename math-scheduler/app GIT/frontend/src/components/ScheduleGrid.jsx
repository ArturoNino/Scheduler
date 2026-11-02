import { exportarExcel } from "../utils/exportarExcel.js";
import { etiquetaGrupo } from "../utils/filtros.js";

/**
 * Cuadrícula día × franja con las sesiones asignadas.
 *
 * `horario` llega YA filtrado (por grupo o por semestre) desde App.jsx, así
 * que esta tabla solo dibuja lo que recibe. `sufijoArchivo` se agrega al
 * nombre del Excel exportado (p. ej. "_semestre_3") para no confundir una
 * vista filtrada con la programación completa.
 */
export default function ScheduleGrid({ horario, dias, horas, sufijoArchivo = "" }) {
  if (!horario || horario.length === 0) {
    return <p className="muted">No hay sesiones asignadas para mostrar.</p>;
  }

  const celda = (dia, hora) =>
    horario.filter((h) => h.dia === dia && h.hora === hora);

  function handleExportar() {
    const columnas = ["Materia", "Semestre", "Grupo", "Tipo de salón", "Día", "Franja"];
    const filas = [...horario]
      .sort((a, b) => a.materia.localeCompare(b.materia) || a.grupo - b.grupo)
      .map((h) => ({
        Materia: h.materia,
        Semestre: h.semestre ?? "",
        Grupo: h.grupo + 1,
        "Tipo de salón": h.tipo_salon,
        "Día": h.dia,
        "Franja": h.hora,
      }));
    exportarExcel(`horario_generado${sufijoArchivo}`, columnas, filas, "Horario");
  }

  return (
    <div>
      <div className="table-toolbar">
        <button type="button" className="export-excel-btn" onClick={handleExportar}>
          ⬇ Excel
        </button>
      </div>
      <div className="table-scroll">
        <table className="grid-table">
        <thead>
          <tr>
            <th>Franja</th>
            {dias.map((d) => (
              <th key={d}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {horas.map((h) => (
            <tr key={h}>
              <td className="hora-col">{h}</td>
              {dias.map((d) => {
                const items = celda(d, h);
                return (
                  <td key={d} className="celda-horario">
                    {items.map((it, idx) => (
                      <div
                        key={idx}
                        className={`sesion-chip ${it.tipo_salon}`}
                        title={`${it.materia} — ${etiquetaGrupo(it.grupo)}${
                          it.semestre != null ? ` — Semestre ${it.semestre}` : ""
                        }`}
                      >
                        <strong>{it.materia}</strong>
                        <span>
                          G{it.grupo + 1}
                          {it.semestre != null ? ` · S${it.semestre}` : ""} · {it.tipo_salon}
                        </span>
                      </div>
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
