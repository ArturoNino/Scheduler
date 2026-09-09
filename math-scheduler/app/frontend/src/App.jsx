import { useState } from "react";
import ProjectionPanel from "./components/ProjectionPanel.jsx";
import ConfigPanel from "./components/ConfigPanel.jsx";
import KpiPanel from "./components/KpiPanel.jsx";
import ScheduleGrid from "./components/ScheduleGrid.jsx";
import SummaryTable from "./components/SummaryTable.jsx";
import RoomUsage from "./components/RoomUsage.jsx";
import { solve } from "./api.js";
import logoUniversidad from "./assets/logo-universidad.jpeg";
import logoCienciaDatos from "./assets/logo-ciencia-datos.jpeg";

const TABS = ["Horario", "Resumen por grupo", "Uso de salones"];

export default function App() {
  const [config, setConfig] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [solving, setSolving] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(TABS[0]);

  function handleProyeccionGenerada(res) {
    setResultado(null);
    setError(null);
    setConfig({
      dataset_id: res.dataset_id,
      dias: res.dias_default,
      horas: res.horas_default,
      disponibilidad: res.disponibilidad_default,
      penalizacion: 10,
      activar_franja_fija: true,
      activar_franja_18_20: true,
    });
  }

  async function handleSolve() {
    setSolving(true);
    setError(null);
    try {
      const res = await solve(config);
      setResultado(res);
      if (!res.factible) {
        setError(res.mensaje || "El solver no encontró una solución factible.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSolving(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <img
          src={logoUniversidad}
          alt="Universidad Externado de Colombia — Departamento de Matemáticas"
          className="brand-logo brand-logo-wide"
        />
        <div className="app-header-text">
          <h1>Optimizador de Horarios</h1>
          <p className="muted">
            Departamento de Matemáticas — Universidad Externado de Colombia · 2026-1
          </p>
        </div>
        <img
          src={logoCienciaDatos}
          alt="Ciencia de Datos — Universidad Externado"
          className="brand-logo brand-logo-badge"
        />
      </header>

      <ProjectionPanel onGenerated={handleProyeccionGenerada} />

      {config && (
        <ConfigPanel
          config={config}
          setConfig={setConfig}
          onSolve={handleSolve}
          solving={solving}
        />
      )}

      {error && <div className="card error-card">{error}</div>}

      {resultado && resultado.factible && (
        <div className="card">
          <h2>3. Resultados</h2>
          <KpiPanel kpis={resultado.kpis} tiempo={resultado.tiempo_segundos} />

          <div className="tabs">
            {TABS.map((t) => (
              <button
                key={t}
                className={`tab-btn ${tab === t ? "active" : ""}`}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "Horario" && (
            <ScheduleGrid
              horario={resultado.horario}
              dias={config.dias}
              horas={config.horas}
            />
          )}
          {tab === "Resumen por grupo" && (
            <SummaryTable resumen={resultado.resumen} />
          )}
          {tab === "Uso de salones" && (
            <RoomUsage usoSalones={resultado.uso_salones} />
          )}
        </div>
      )}
    </div>
  );
}
