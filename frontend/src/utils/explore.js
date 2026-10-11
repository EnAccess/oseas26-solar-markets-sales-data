export function cellCenter(feature) {
  const g = feature.geometry;
  if (!g) return null;
  if (g.type === "Point") return g.coordinates;
  const rings = g.type === "Polygon" ? g.coordinates : g.coordinates.flat();
  let sx = 0, sy = 0, n = 0;
  for (const ring of rings) {
    for (const [x, y] of ring) {
      sx += x;
      sy += y;
      n++;
    }
  }
  return n ? [sx / n, sy / n] : null;
}

export function kmBetween(a, b) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLng = toRad(b[0] - a[0]);
  const lat = toRad((a[1] + b[1]) / 2);
  const x = dLng * Math.cos(lat);
  return Math.sqrt(x * x + dLat * dLat) * R;
}

export function neighborsWithin(features, centerFeature, radiusKm) {
  const center = cellCenter(centerFeature);
  if (!center) return [];
  const out = [];
  for (const f of features) {
    const c = cellCenter(f);
    if (!c) continue;
    const d = kmBetween(center, c);
    if (d <= radiusKm) out.push({ feature: f, distanceKm: d });
  }
  return out;
}

function mean(xs) {
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function p90(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(s.length * 0.9))];
}

export function summarizeNeighborhood(features, centerFeature, radiusKm, stats) {
  const list = neighborsWithin(features, centerFeature, radiusKm);
  const values = list.map((x) => x.feature.properties.value).filter((v) => v != null);
  const centerProps = centerFeature.properties;

  const dark = values.filter((v) => v < 0.5).length;
  const bright = values.filter((v) => v >= 3).length;
  const mid = values.length - dark - bright;

  return {
    centerId: centerProps.cell_id,
    centerValue: centerProps.value,
    radiusKm,
    cellCount: list.length,
    meanValue: mean(values),
    medianValue: median(values),
    p90Value: p90(values),
    maxValue: values.length ? Math.max(...values) : null,
    minValue: values.length ? Math.min(...values) : null,
    darkCells: dark,
    midCells: mid,
    brightCells: bright,
    sortedByDistance: list.sort((a, b) => a.distanceKm - b.distanceKm),
    countryMeanPenetration: stats?.avg_predicted_penetration ?? null,
  };
}

export function findById(features, query) {
  if (!query) return null;
  const q = query.trim().toUpperCase();
  return features.find(
    (feature) => String(feature.properties.cell_id || "").toUpperCase() === q,
  ) || null;
}