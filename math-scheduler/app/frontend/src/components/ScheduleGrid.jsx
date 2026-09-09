import { exportarExcel } from "../utils/exportarExcel.js";

export default function ScheduleGrid({ horario, dias, horas }) {
  if (!horario || horario.length === 0) {
    return <p className="muted">No hay sesiones asignadas para mostrar.</p>;
  }

  const celda = (dia, hora) =>
    horario.filter((h) => h.dia === dia && h.hora === hora);

  function handleExportar() {
    const columnas = ["Materia", "Grupo", "Tipo de salón", "Día", "Franja"];
    const filas = [...horario]
      .sort((a, b) => a.materia.localeCompare(b.materia) || a.grupo - b.grupo)
      .map((h) => ({
        Materia: h.materia,
        Grupo: h.grupo,
        "Tipo de salón": h.tipo_salon,
        "Día": h.dia,
        "Franja": h.hora,
      }));
    exportarExcel("horario_generado", columnas, filas, "Horario");
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
                        title={`${it.materia} — Grupo ${it.grupo}`}
                      >
                        <strong>{it.materia}</strong>
                        <span>
                          G{it.grupo} · {it.tipo_salon}
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
