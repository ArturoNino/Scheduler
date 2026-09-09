import ExportExcelButton from "./ExportExcelButton.jsx";

export default function ScrollableTable({ columnas, filas, maxHeight = "420px", filename }) {
  if (!filas || filas.length === 0) {
    return <p className="muted">Sin filas para mostrar.</p>;
  }

  return (
    <div>
      {filename && (
        <div className="table-toolbar">
          <ExportExcelButton filename={filename} columnas={columnas} filas={filas} />
        </div>
      )}
      <div className="table-scroll" style={{ maxHeight, overflowY: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              {columnas.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((row, idx) => (
              <tr key={idx}>
                {columnas.map((c) => (
                  <td key={c}>{String(row[c] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
