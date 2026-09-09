const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getHealth() {
  const res = await fetch(`${BASE_URL}/api/health`);
  return handle(res);
}

export async function getDefaultConfig() {
  const res = await fetch(`${BASE_URL}/api/config/default`);
  return handle(res);
}

export async function uploadDataset(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE_URL}/api/dataset/upload`, {
    method: "POST",
    body: formData,
  });
  return handle(res);
}

export async function generarProyeccion(
  archivo,
  { capOtras = 35, capCore = 20, redondeo = "round" } = {}
) {
  const formData = new FormData();
  formData.append("archivo", archivo);
  formData.append("cap_otras", String(capOtras));
  formData.append("cap_core", String(capCore));
  formData.append("redondeo", redondeo);
  const res = await fetch(`${BASE_URL}/api/proyeccion/generar`, {
    method: "POST",
    body: formData,
  });
  return handle(res);
}

export async function solve(config) {
  const res = await fetch(`${BASE_URL}/api/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  return handle(res);
}
