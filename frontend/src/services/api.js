import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 60000,
});
const get = (url, params) => http.get(url, { params }).then((r) => r.data);

export const api = {
  countries: () => get("/api/countries"),
  meta: (country) => get("/api/meta", { country }),
  layers: () => get("/api/layers"),
  layer: (id, country) => get(`/api/map/layer/${id}`, { country }),
  infrastructure: (country) => get("/api/map/infrastructure", { country }),
  gridCheck: (lat, lon, radiusKm, country) =>
    get("/api/grid/check", {
      lat,
      lon,
      radius_km: radiusKm,
      country,
    }),
  cell: (id, threshold) => get(`/api/cells/${id}`, { threshold }),
  performance: (country) => get("/api/model/performance", { country }),
  features: (country) => get("/api/model/features", { country }),
  statistics: (country, threshold) =>
    get("/api/statistics", { country, threshold }),
  gogla: (country) => get("/api/gogla/comparison", { country }),
  dataSources: () => get("/api/data-sources"),
  limitations: () => get("/api/limitations"),
};

export function errorMessage(err) {
  if (err?.response) {
    const d = err.response.data?.detail;
    return `The server responded with ${err.response.status}${d ? `: ${typeof d === "string" ? d : JSON.stringify(d)}` : ""}`;
  }
  if (err?.code === "ECONNABORTED") return "The request timed out.";
  return "Cannot reach the API. Start the backend with: uvicorn app.main:app --reload";
}
