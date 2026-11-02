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

        <label className="checkbox">
          <input
            type="checkbox"
            checked={config.activar_cruce_semestre}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                activar_cruce_semestre: e.target.checked,
              }))
            }
          />
          Evitar que se crucen materias del mismo semestre
        </label>

        <label>
          Penalización por cruce de semestre
          <input
            type="number"
            value={config.penalizacion_cruce}
            disabled={!config.activar_cruce_semestre}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                penalizacion_cruce: Number(e.target.value),
              }))
            }
          />
        </label>

        <label>
          Formulación del cruce de semestre
          <select
            value={config.modo_cruce_semestre}
            disabled={!config.activar_cruce_semestre}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                modo_cruce_semestre: e.target.value,
              }))
            }
          >
            <option value="binario">Binario (exacta)</option>
            <option value="fraccion">Fracción (más liviana)</option>
          </select>
        </label>
      </div>

      <h3 className="config-subtitulo">Correcciones de los tutores</h3>
      <div className="row">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={config.activar_restricciones_materia}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                activar_restricciones_materia: e.target.checked,
              }))
            }
          />
          Aplicar franjas y días por materia (Cálculo, Discretas, Álgebra,
          Probabilidad, Métodos Numéricos y Optimización solo en la mañana;
          Emprendimiento solo Lun-Mié-Vie; Marketing, Healthtech y Defi /
          Estadística / Neurociencias en sus franjas)
        </label>

        <label>
          Penalización por concentrar grupos de una materia (0 = desactivada)
          <input
            type="number"
            min="0"
            step="0.1"
            value={config.penalizacion_dispersion}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                penalizacion_dispersion: Number(e.target.value),
              }))
            }
          />
        </label>

        <label>
          Holgura K (grupos extra permitidos por franja)
          <input
            type="number"
            min="0"
            step="1"
            value={config.holgura_k}
            disabled={config.penalizacion_dispersion <= 0}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                holgura_k: Math.max(0, Math.trunc(Number(e.target.value))),
              }))
            }
          />
        </label>

        <label>
          Tiempo límite del solver (segundos)
          <input
            type="number"
            min="1"
            step="1"
            value={config.tiempo_limite_segundos}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                tiempo_limite_segundos: Math.max(1, Number(e.target.value)),
              }))
            }
          />
        </label>
      </div>

      <button className="primary" onClick={onSolve} disabled={solving}>
        {solving ? "Resolviendo…" : "Ejecutar solver"}
      </button>
    </div>
  );
}
