export default function ConfigPanel({ config, setConfig, onSolve, solving }) {
  function updateDia(dia, campo, valor) {
    setConfig((prev) => ({
      ...prev,
      disponibilidad: {
        ...prev.disponibilidad,
        [dia]: {
          ...prev.disponibilidad[dia],
          [campo]: Number(valor),
        },
      },
    }));
  }

  return (
    <div className="card">
      <h2>2. Configurar disponibilidad de salones</h2>
      <table className="config-table">
        <thead>
          <tr>
            <th>Día</th>
            <th>Salones teóricos</th>
            <th>Salas de cómputo</th>
          </tr>
        </thead>
        <tbody>
          {config.dias.map((dia) => (
            <tr key={dia}>
              <td>{dia}</td>
              <td>
                <input
                  type="number"
                  min="0"
                  value={config.disponibilidad[dia]?.teorico ?? 0}
                  onChange={(e) => updateDia(dia, "teorico", e.target.value)}
                />
              </td>
              <td>
                <input
                  type="number"
                  min="0"
                  value={config.disponibilidad[dia]?.computo ?? 0}
                  onChange={(e) => updateDia(dia, "computo", e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="row">
        <label>
          Penalización por sesión no asignada
          <input
            type="number"
            value={config.penalizacion}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                penalizacion: Number(e.target.value),
              }))
            }
          />
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={config.activar_franja_fija}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                activar_franja_fija: e.target.checked,
              }))
            }
          />
          Agrupar sesiones de cada grupo en una franja fija (SC10-SC11)
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={config.activar_franja_18_20}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                activar_franja_18_20: e.target.checked,
              }))
            }
          />
          Restringir franja 18-20 a materias específicas (Ciberseguridad,
          Disciplina 4, Talleres)
        </label>
      </div>

      <button className="primary" onClick={onSolve} disabled={solving}>
        {solving ? "Resolviendo…" : "Ejecutar solver"}
      </button>
    </div>
  );
}
