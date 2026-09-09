import { useState } from "react";
import { generarProyeccion } from "../api.js";
import ScrollableTable from "./ScrollableTable.jsx";

export default function ProjectionPanel({ onGenerated }) {
  const [archivo, setArchivo] = useState(null);
  const [capOtras, setCapOtras] = useState(35);
  const [capCore, setCapCore] = useState(20);
  const [redondeo, setRedondeo] = useState("round");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [tab, setTab] = useState("solver"); // "solver" | "detalle"
  const [verMateriasCore, setVerMateriasCore] = useState(false);

  async function handleGenerar() {
    if (!archivo) {
      setError("Sube el archivo con la matrícula y las sesiones por grupo.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await generarProyeccion(archivo, {
        capOtras: Number(capOtras),
        capCore: Number(capCore),
        redondeo,
      });
      setResultado(res);
      onGenerated(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2>1. Generar dataset desde proyección de matrícula</h2>
      <p className="muted">
        Sube un solo archivo con, por materia: <code>codigo</code> (el
        código MA#### del plan de estudios — ya no el nombre en texto
        libre, así se evitan errores de tildes/mayúsculas),{" "}
        <code>estudiantes_actuales</code>, <code>porcentaje_perdida</code>,{" "}
        <code>inscritos_nuevos</code>, <code>computo</code> (sesiones de
        cómputo por grupo), <code>teoricos</code> (sesiones teóricas por
        grupo) y <code>sesiones por grupo</code> (total). Se proyectan
        estudiantes, se calculan los grupos necesarios, y se arma el
        dataset listo para el solver.
      </p>

      <div className="row">
        <label className="file-input">
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => setArchivo(e.target.files[0])}
          />
          {archivo ? archivo.name : "Seleccionar archivo .xlsx"}
        </label>
      </div>

      <div className="row">
        <label>
          Capacidad por grupo — materias core
          <input
            type="number"
            min="1"
            value={capCore}
            onChange={(e) => setCapCore(e.target.value)}
          />
        </label>
        <label>
          Capacidad por grupo — resto de materias
          <input
            type="number"
            min="1"
            value={capOtras}
            onChange={(e) => setCapOtras(e.target.value)}
          />
        </label>
        <label>
          Redondeo de proyección
          <select value={redondeo} onChange={(e) => setRedondeo(e.target.value)}>
            <option value="round">Redondeo normal</option>
            <option value="ceil">Redondeo hacia arriba (ceil)</option>
          </select>
        </label>
      </div>

      <p className="muted" style={{ marginTop: -8, marginBottom: 12 }}>
        "Materias core" son Cálculo, Programación, Machine Learning, etc.
        (la lista fija del currículo) — antes tenían un tope de 20
        estudiantes por grupo sin poder cambiarlo; ahora lo puedes ajustar
        arriba. Genera el dataset una vez para ver la lista completa.
      </p>

      <button className="primary" onClick={handleGenerar} disabled={loading}>
        {loading ? "Generando…" : "Generar dataset"}
      </button>

      {error && <p className="error">{error}</p>}

      {resultado && (
        <div style={{ marginTop: 20 }}>
          <div className="row" style={{ marginTop: 0 }}>
            <button
              type="button"
              className="tab-btn"
              style={{ border: "1px solid var(--border)", borderRadius: 6 }}
              onClick={() => setVerMateriasCore((v) => !v)}
            >
              {verMateriasCore ? "Ocultar" : "Ver"} materias core (
              {(resultado.materias_core || []).length}) — tope usado:{" "}
              {resultado.cap_core_usado ?? "?"}
            </button>
          </div>

          {verMateriasCore && (
            <div className="card" style={{ marginTop: 8, marginBottom: 12 }}>
              <ul style={{ columns: 2, marginTop: 0, marginBottom: 0 }}>
                {(resultado.materias_core || []).map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}

          {(resultado.advertencias_prerrequisitos || []).length > 0 && (
            <div className="warning" style={{ padding: 12, borderRadius: 8, marginBottom: 12 }}>
              <strong>Prerrequisitos que no se pudieron verificar</strong> (probablemente
              mezclaste códigos de dos planes de estudio distintos para la misma
              materia — revisa que estés usando el código del plan vigente en
              todas las filas):
              <ul>
                {resultado.advertencias_prerrequisitos.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          {(resultado.materias_sin_catalogo || []).length > 0 && (
            <div className="warning" style={{ padding: 12, borderRadius: 8, marginBottom: 12 }}>
              <strong>Materias sin sesiones definidas en el catálogo</strong> (quedaron
              con 0 sesiones, complétalas en el catálogo si van al solver):
              <ul>
                {resultado.materias_sin_catalogo.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="tabs">
            <button
              className={`tab-btn ${tab === "solver" ? "active" : ""}`}
              onClick={() => setTab("solver")}
            >
              Dataset para el solver ({resultado.filas})
            </button>
            <button
              className={`tab-btn ${tab === "detalle" ? "active" : ""}`}
              onClick={() => setTab("detalle")}
            >
              Detalle de proyección
            </button>
          </div>

          {tab === "solver" ? (
            <ScrollableTable
              columnas={resultado.columnas_dataset}
              filas={resultado.dataset_solver}
              filename="dataset_solver"
            />
          ) : (
            <ScrollableTable
              columnas={resultado.columnas_detalle}
              filas={resultado.proyeccion_detallada}
              filename="proyeccion_detallada"
            />
          )}
        </div>
      )}
    </div>
  );
}
