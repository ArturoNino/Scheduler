import { exportarExcel } from "../utils/exportarExcel.js";

export default function RoomUsage({ usoSalones }) {
  if (!usoSalones || usoSalones.length === 0) return null;

  function handleExportar() {
    const columnas = ["Día", "Franja", "Teórico usados", "Teórico disponibles", "Cómputo usados", "Cómputo disponibles"];
    const filas = usoSalones.map((u) => ({
      "Día": u.dia,
      "Franja": u.hora,
      "Teórico usados": u.teorico_usados,
      "Teórico disponibles": u.teorico_disponibles,
      "Cómputo usados": u.computo_usados,
      "Cómputo disponibles": u.computo_disponibles,
    }));
    exportarExcel("uso_de_salones", columnas, filas, "Uso de salones");
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
              <th>Día</th>
              <th>Franja</th>
              <th>Teórico (uso/disp.)</th>
              <th>Cómputo (uso/disp.)</th>
            </tr>
          </thead>
          <tbody>
            {usoSalones.map((u, idx) => (
              <tr key={idx}>
                <td>{u.dia}</td>
                <td>{u.hora}</td>
                <td>
                  {u.teorico_usados}/{u.teorico_disponibles}
                </td>
                <td>
                  {u.computo_usados}/{u.computo_disponibles}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
