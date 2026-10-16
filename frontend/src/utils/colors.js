// Sequential palettes per layer (light -> dark). Cells without data use NO_DATA.
export const PALETTES = {
  market_gap: ["#f7fee7", "#d9f99d", "#a3e635", "#4d7c0f", "#064e3b"],
  population: ["#f5f3ff", "#ddd6fe", "#a78bfa", "#6d28d9", "#3b0764"],
  population_total: ["#f5f3ff", "#ddd6fe", "#a78bfa", "#6d28d9", "#3b0764"],
  grid: ["#f0f9ff", "#bae6fd", "#38bdf8", "#0369a1", "#0c2d48"],
  survey_solar: ["#fefce8", "#fde68a", "#f59e0b", "#b45309", "#713f12"],
  solar_penetration: ["#ecfdf5", "#a7f3d0", "#34d399", "#047857", "#064e3b"],
  relative_wealth: ["#9f1239", "#f43f5e", "#fef3c7", "#34d399", "#065f46"],
  night_lights: ["#0b0724", "#2c115f", "#721f81", "#b63679", "#e65164", "#fb8b38", "#fecb2f", "#f5f5c0"],
};
export const NO_DATA = "#d1d5db";

const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

export function rampColor(stops, t) {
  if (t == null || Number.isNaN(t)) return NO_DATA;
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const a = rgb(stops[i]);
  const b = rgb(stops[i + 1]);
  return "#" + a.map((v, k) => Math.round(v + (b[k] - v) * f).toString(16).padStart(2, "0")).join("");
}

export const gradientCss = (stops) => `linear-gradient(to right, ${stops.join(",")})`;

/** Map a value to 0-1 using the layer's metadata (linear or log scale). Null stays null. */
export function normalizer(meta) {
  if (meta.scale === "log") {
    const floor = Math.max(meta.min, 1e-3);
    const lo = Math.log(floor);
    const span = Math.log(Math.max(meta.max, floor * 1.1)) - lo || 1;
    return (v) => (v == null || Number.isNaN(v) ? null : (Math.log(Math.max(v, floor)) - lo) / span);
  }
  const span = meta.max - meta.min || 1;
  return (v) => (v == null || Number.isNaN(v) ? null : (v - meta.min) / span);
}
