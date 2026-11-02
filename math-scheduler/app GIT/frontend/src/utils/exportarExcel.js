import * as XLSX from "xlsx";

/**
 * Descarga un array de filas (objetos) como archivo .xlsx, respetando
 * el orden de columnas dado.
 *
 * @param {string} filename - nombre del archivo (con o sin .xlsx)
 * @param {string[]} columnas - nombres de columna, en el orden que se quiere exportar
 * @param {object[]} filas - filas a exportar; se toma row[col] para cada columna
 * @param {string} [hoja] - nombre de la hoja dentro del libro
 */
export function exportarExcel(filename, columnas, filas, hoja = "Datos") {
  if (!filas || filas.length === 0) return;

  const datos = filas.map((row) => {
    const obj = {};
    columnas.forEach((col) => {
      obj[col] = row[col] ?? "";
    });
    return obj;
  });

  const worksheet = XLSX.utils.json_to_sheet(datos, { header: columnas });
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, hoja);

  const nombreFinal = filename.toLowerCase().endsWith(".xlsx") ? filename : `${filename}.xlsx`;
  XLSX.writeFile(workbook, nombreFinal);
}
