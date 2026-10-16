import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 60000,
});
const get = (url, params) => http.get(url, { params }).then((r) => r.data);
const post = (url, body, params, config = {}) => http.post(url, body, { params, ...config }).then((r) => r.data);

export const api = {
  countries: () => get("/api/countries"),
  meta: (country) => get("/api/meta", { country }),
  layers: (country) => get("/api/layers", { country }),
  layer: (id, country) => get(`/api/map/layer/${id}`, { country }),
  infrastructure: (country) => get("/api/map/infrastructure", { country }),
  cell: (id, threshold) => get(`/api/cells/${id}`, { threshold }),
  performance: (country) => get("/api/model/performance", { country }),
  features: (country) => get("/api/model/features", { country }),
  statistics: (country, threshold) => get("/api/statistics", { country, threshold }),
  gogla: (country) => get("/api/gogla/comparison", { country }),
  dataSources: (country) => get("/api/data-sources", { country }),
  limitations: () => get("/api/limitations"),
  searchLocation: (q, country) => get("/api/locations/search", { q, country }),
  reportSummary: (cellIds, threshold, country, title) =>
    post("/api/reports/summary", { cell_ids: cellIds, threshold, title }, { country }),
  reportFile: (format, cellIds, threshold, country, title) =>
    post(`/api/reports/${format}`, { cell_ids: cellIds, threshold, title }, { country }, { responseType: "blob", timeout: 120000 }),
  assistantStatus: () => get("/api/assistant/status"),
  ask: (body, country) => post("/api/assistant/ask", body, { country }, { timeout: 120000 }),
};

/** Save a Blob as a file in the browser. */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorMessage(err) {
  if (err?.response) {
    const d = err.response.data?.detail;
    const detail = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : null;
    return detail || `The server responded with ${err.response.status}.`;
  }
  if (err?.code === "ECONNABORTED") return "The request timed out.";
  return "Cannot reach the API. Start the backend with: uvicorn app.main:app --reload";
}
