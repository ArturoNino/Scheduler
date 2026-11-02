import {
  MODO,
  SIN_SEMESTRE,
  descripcionFiltro,
  etiquetaGrupo,
  etiquetaSemestre,
  filtroParaModo,
  opcionesGrupo,
  opcionesSemestre,
} from "../utils/filtros.js";

/**
 * Barra con los dos filtros independientes de visualización:
 *   [Ver todo]  [Visualización por grupo]  [Visualización por semestre]
 * Al activar uno de los dos aparecen las opciones (grupos o semestres)
 * disponibles en la programación generada.
 *
 * Props:
 *   filtro / setFiltro  estado { modo, valor } (ver utils/filtros.js)
 *   resumen             filas del resumen (una por materia-grupo): de ahí salen las opciones
 *   mostradas / total   cantidad de sesiones visibles vs. totales
 */
export default function FiltroVisualizacion({ filtro, setFiltro, resumen, mostradas, total }) {
  const grupos = opcionesGrupo(resumen);
  const semestres = opcionesSemestre(resumen);

  const opciones = filtro.modo === MODO.GRUPO ? grupos : semestres;
  const etiqueta = filtro.modo === MODO.GRUPO ? etiquetaGrupo : etiquetaSemestre;

  return (
    <div className="filtro-panel">
      <div className="filtro-botones" role="group" aria-label="Filtros de visualización">
        <button
          type="button"
          className={`filtro-btn ${filtro.modo === MODO.TODO ? "active" : ""}`}
          onClick={() => setFiltro(filtroParaModo(MODO.TODO, resumen))}
        >
          Ver todo
        </button>
        <button
          type="button"
          className={`filtro-btn filtro-grupo ${filtro.modo === MODO.GRUPO ? "active" : ""}`}
          onClick={() => setFiltro(filtroParaModo(MODO.GRUPO, resumen))}
          disabled={grupos.length === 0}
        >
          👥 Visualización por grupo
        </button>
        <button
          type="button"
          className={`filtro-btn filtro-semestre ${filtro.modo === MODO.SEMESTRE ? "active" : ""}`}
          onClick={() => setFiltro(filtroParaModo(MODO.SEMESTRE, resumen))}
          disabled={semestres.every((s) => s === SIN_SEMESTRE)}
        >
          🎓 Visualización por semestre
        </button>
      </div>

      {filtro.modo !== MODO.TODO && (
        <div className="filtro-opciones">
          <span className="muted">
            {filtro.modo === MODO.GRUPO ? "Selecciona un grupo:" : "Selecciona un semestre:"}
          </span>
          {opciones.map((op) => (
            <button
              key={String(op)}
              type="button"
              className={`chip-opcion ${filtro.valor === op ? "active" : ""}`}
              onClick={() => setFiltro({ modo: filtro.modo, valor: op })}
            >
              {etiqueta(op)}
            </button>
          ))}
        </div>
      )}

      <p className="muted filtro-estado">
        <strong>{descripcionFiltro(filtro)}</strong> · {mostradas} de {total} sesiones
      </p>
    </div>
  );
}
