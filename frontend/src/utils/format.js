export const fmtInt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-US"));
export const fmtNum = (n, d = 2) => (n == null ? "–" : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const fmtPct = (n, d = 0) => (n == null ? "–" : `${(n * 100).toFixed(d)}%`);
export const fmtCompact = (n) =>
  n == null ? "–" : Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
/** 0-1 score -> "52 / 100" (integers only: the score is relative, not precise). */
export const fmtScore = (n) => (n == null ? "No score" : `${Math.round(n * 100)} / 100`);
export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" }) : "–");

/** Value with unit as shown in layer metadata ("people/km²", "km", "% of households", ...). */
export function fmtLayerValue(value, unit) {
  if (value == null) return "No data";
  if (unit?.startsWith("%")) return `${fmtNum(value, 1)}%`;
  if (unit?.startsWith("score")) return `${Math.round(value)} / 100`;
  const decimals = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  return `${fmtNum(value, decimals)} ${unit ?? ""}`.trim();
}
