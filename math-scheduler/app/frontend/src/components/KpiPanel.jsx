export default function KpiPanel({ kpis, tiempo }) {
  if (!kpis) return null;

  const items = [
    ["Grupos totales", kpis.grupos_totales],
    ["Asignaciones completas", kpis.asignaciones_completas],
    ["Asignaciones incompletas", kpis.asignaciones_incompletas],
    ["% completitud", `${kpis.porcentaje_completitud}%`],
    ["Sesiones teóricas totales", kpis.sesiones_teoricas_totales],
    ["Sesiones cómputo totales", kpis.sesiones_computo_totales],
    ["Tiempo de solución", `${tiempo}s`],
  ];

  return (
    <div className="kpi-grid">
      {items.map(([label, valor]) => (
        <div className="kpi-box" key={label}>
          <div className="kpi-value">{valor}</div>
          <div className="kpi-label">{label}</div>
        </div>
      ))}
    </div>
  );
}
