import { useState } from "react";
import ProjectionPanel from "./components/ProjectionPanel.jsx";
import ConfigPanel from "./components/ConfigPanel.jsx";
import KpiPanel from "./components/KpiPanel.jsx";
import FiltroVisualizacion from "./components/FiltroVisualizacion.jsx";
import ScheduleGrid from "./components/ScheduleGrid.jsx";
import SummaryTable from "./components/SummaryTable.jsx";
import RoomUsage from "./components/RoomUsage.jsx";
import { solve } from "./api.js";
import { FILTRO_INICIAL, aplicarFiltro, sufijoArchivo } from "./utils/filtros.js";
import logoUniversidad from "./assets/logo-universidad.jpeg";
import logoCienciaDatos from "./assets/logo-ciencia-datos.jpeg";

const TABS = ["Horario", "Resumen por grupo", "Uso de salones"];

export default function App() {
  const [config, setConfig] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [solving, setSolving] = useState(false);
  const [error, setError] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [tab, setTab] = useState(TABS[0]);
  // Filtro de visualización: { modo: "todo" | "grupo" | "semestre", valor }
  const [filtro, setFiltro] = useState(FILTRO_INICIAL);

  function handleProyeccionGenerada(res) {
    setResultado(null);
    setFiltro(FILTRO_INICIAL);
    setError(null);
    setConfig({
      dataset_id: res.dataset_id,
      dias: res.dias_default,
      horas: res.horas_default,
      disponibilidad: res.disponibilidad_default,
      penalizacion: 10,
      activar_franja_fija: true,
      activar_franja_18_20: true,
      activar_cruce_semestre: true,
      penalizacion_cruce: 5,
      modo_cruce_semestre: "binario",
      activar_restricciones_materia: true,
      penalizacion_dispersion: 0.5,
      holgura_k: 0,
      tiempo_limite_segundos: 120,
    });
  }

  async function handleSolve() {
    setSolving(true);
    setError(null);
    setAviso(null);
    try {
      const res = await solve(config);
      setResultado(res);
      setFiltro(FILTRO_INICIAL);
      if (!res.factible) {
        setError(res.mensaje || "El solver no encontró una solución factible.");
      } else if (res.mensaje) {
        setAviso(res.mensaje);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSolving(false);
    }
  }

  // El filtro se aplica sobre la programación ya generada (no vuelve a llamar al solver).
  const horarioFiltrado = resultado ? aplicarFiltro(resultado.horario, filtro) : [];
  const resumenFiltrado = resultado ? aplicarFiltro(resultado.resumen, filtro) : [];

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
      {aviso && (
        <div className="card warning" style={{ padding: 12 }}>
          ℹ️ {aviso}
        </div>
      )}

      {resultado && resultado.avisos && resultado.avisos.length > 0 && (
        <details className="card warning avisos-modelo">
          <summary>
            Notas del modelo ({resultado.avisos.length}) — reglas que no encontraron su materia
          </summary>
          <ul>
            {resultado.avisos.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      )}

      {resultado && resultado.factible && (
        <div className="card">
          <h2>3. Resultados</h2>
          <KpiPanel kpis={resultado.kpis} tiempo={resultado.tiempo_segundos} />

          <FiltroVisualizacion
            filtro={filtro}
            setFiltro={setFiltro}
            resumen={resultado.resumen}
            mostradas={horarioFiltrado.length}
            total={resultado.horario.length}
          />

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
              horario={horarioFiltrado}
              dias={config.dias}
              horas={config.horas}
              sufijoArchivo={sufijoArchivo(filtro)}
            />
          )}
          {tab === "Resumen por grupo" && (
            <SummaryTable
              resumen={resumenFiltrado}
              sufijoArchivo={sufijoArchivo(filtro)}
            />
          )}
          {tab === "Uso de salones" && (
            <>
              {filtro.modo !== "todo" && (
                <p className="muted">
                  El uso de salones es global: no se filtra por grupo ni por semestre.
                </p>
              )}
              <RoomUsage usoSalones={resultado.uso_salones} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
