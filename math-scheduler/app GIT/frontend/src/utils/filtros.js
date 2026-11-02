/**
 * Filtros de visualización del horario generado.
 *
 * Hay DOS filtros independientes (solo uno activo a la vez):
 *   - "grupo":    muestra únicamente las sesiones del grupo elegido
 *                 (el grupo N de cada materia).
 *   - "semestre": muestra únicamente las materias/grupos del semestre elegido.
 * "todo" muestra la programación completa.
 *
 * Los filtros operan sobre las filas que ya devuelve el backend
 * (horario y resumen: ambos traen `grupo` y `semestre`), así que no
 * hace falta volver a llamar al solver.
 *
 * Nota: internamente `grupo` va desde 0 (índice del modelo); en pantalla
 * se muestra desde 1 con `etiquetaGrupo`, igual que "GRUPO 1" en la
 * programación de la universidad.
 */

export const MODO = { TODO: "todo", GRUPO: "grupo", SEMESTRE: "semestre" };

export const SIN_SEMESTRE = "sin";

export const FILTRO_INICIAL = { modo: MODO.TODO, valor: null };

export const etiquetaGrupo = (g) => `Grupo ${Number(g) + 1}`;

export const etiquetaSemestre = (s) =>
  s === SIN_SEMESTRE ? "Sin semestre" : `Semestre ${s}`;

/** Grupos distintos presentes en las filas, ordenados. */
export function opcionesGrupo(filas) {
  return [...new Set((filas || []).map((f) => f.grupo))].sort((a, b) => a - b);
}

/** Semestres distintos presentes en las filas (+ "sin" si alguna materia no tiene semestre). */
export function opcionesSemestre(filas) {
  const lista = filas || [];
  const semestres = [
    ...new Set(lista.filter((f) => f.semestre != null).map((f) => f.semestre)),
  ].sort((a, b) => a - b);
  if (lista.some((f) => f.semestre == null)) semestres.push(SIN_SEMESTRE);
  return semestres;
}

/** Filtro con el primer valor disponible para el modo pedido. */
export function filtroParaModo(modo, filas) {
  if (modo === MODO.GRUPO) {
    const ops = opcionesGrupo(filas);
    return { modo, valor: ops.length ? ops[0] : null };
  }
  if (modo === MODO.SEMESTRE) {
    const ops = opcionesSemestre(filas);
    return { modo, valor: ops.length ? ops[0] : null };
  }
  return FILTRO_INICIAL;
}

/** Aplica el filtro a una lista de filas (horario o resumen). */
export function aplicarFiltro(filas, filtro) {
  if (!filas) return [];
  if (!filtro || filtro.modo === MODO.TODO || filtro.valor === null) return filas;
  if (filtro.modo === MODO.GRUPO) {
    return filas.filter((f) => f.grupo === filtro.valor);
  }
  if (filtro.modo === MODO.SEMESTRE) {
    return filtro.valor === SIN_SEMESTRE
      ? filas.filter((f) => f.semestre == null)
      : filas.filter((f) => f.semestre === filtro.valor);
  }
  return filas;
}

/** Texto corto del filtro activo, p. ej. "Grupo 2" o "Semestre 3". */
export function descripcionFiltro(filtro) {
  if (!filtro || filtro.modo === MODO.TODO || filtro.valor === null) return "Programación completa";
  return filtro.modo === MODO.GRUPO
    ? etiquetaGrupo(filtro.valor)
    : etiquetaSemestre(filtro.valor);
}

/** Sufijo para nombres de archivo, p. ej. "_grupo_2" o "_semestre_3". */
export function sufijoArchivo(filtro) {
  if (!filtro || filtro.modo === MODO.TODO || filtro.valor === null) return "";
  return filtro.modo === MODO.GRUPO
    ? `_grupo_${Number(filtro.valor) + 1}`
    : `_semestre_${filtro.valor}`;
}
