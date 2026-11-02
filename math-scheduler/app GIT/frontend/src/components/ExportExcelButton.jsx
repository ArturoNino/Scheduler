import { exportarExcel } from "../utils/exportarExcel.js";

export default function ExportExcelButton({ filename, columnas, filas, hoja, label = "Excel" }) {
  if (!filas || filas.length === 0) return null;

  return (
    <button
      type="button"
      className="export-excel-btn"
      onClick={() => exportarExcel(filename, columnas, filas, hoja)}
      title="Descargar esta tabla como archivo Excel (.xlsx)"
    >
      ⬇ {label}
    </button>
  );
}
