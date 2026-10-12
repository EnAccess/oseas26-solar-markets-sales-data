import { loadData, lookupByCoords } from "rwanda-location-lookup";

export const ADMIN_LEVELS = [
  { id: "province", name: "Province" },
  { id: "district", name: "District" },
  { id: "sector", name: "Sector" },
  { id: "cell", name: "Cell" },
  { id: "village", name: "Village" },
  { id: "grid", name: "5 km analysis grid" },
];

const GRID_LOOKUPS = new Map();
const EARTH_RADIUS_KM = 6371.0088;

export function loadAdminData() {
  return loadData();
}

function sourceFeatures(data, level) {
  if (level === "province") {
    const provinces = new Map();
    const provinceByDistrict = new Map();
    for (const feature of data.cells.features) {
      const props = feature.properties;
      if (props.Prov_ID == null || !props.Province || props.Dist_ID == null) continue;
      provinces.set(String(props.Prov_ID), props.Province);
      provinceByDistrict.set(String(props.Dist_ID), String(props.Prov_ID));
    }

    const districtGroups = new Map();
    for (const feature of data.districts.features) {
      const provinceId = provinceByDistrict.get(String(feature.properties.Dist_ID));
      if (!provinceId) continue;
      const group = districtGroups.get(provinceId) || [];
      group.push(feature.geometry);
      districtGroups.set(provinceId, group);
    }

    return [...provinces].map(([id, name]) => ({
      type: "Feature",
      properties: { Prov_ID: id, Province: name },
      geometry: {
        type: "MultiPolygon",
        coordinates: (districtGroups.get(id) || []).flatMap((geometry) =>
          geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates,
        ),
      },
    }));
  }

  const [collection, idField, nameField] = {
    district: [data.districts, "Dist_ID", "District"],
    sector: [data.sectors, "Sect_ID", "Name"],
    cell: [data.cells, "Cell_ID", "Name"],
    village: [data.villages, "Village_ID", "Name"],
  }[level] || [];

  if (!collection) return [];
  return collection.features.map((feature) => ({
    ...feature,
    properties: {
      ...feature.properties,
      __admin_id: String(feature.properties[idField]),
      __admin_name: feature.properties[nameField],
    },
  }));
}

function areaOfRing(ring) {
  let total = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [lon1, lat1] = ring[index];
    const [lon2, lat2] = ring[index + 1];
    total +=
      ((lon2 - lon1) * Math.PI / 180) *
      (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
  }
  return Math.abs(total * EARTH_RADIUS_KM ** 2 / 2);
}

function geometryArea(geometry) {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.reduce((total, polygon) => {
    const [outer, ...holes] = polygon;
    return total + Math.max(0, areaOfRing(outer) - holes.reduce((sum, ring) => sum + areaOfRing(ring), 0));
  }, 0);
}

function gridCenter(feature) {
  const ring = feature.geometry?.coordinates?.[0];
  if (!ring?.length) return null;
  const points = ring.slice(0, -1);
  return {
    longitude: points.reduce((sum, point) => sum + point[0], 0) / points.length,
    latitude: points.reduce((sum, point) => sum + point[1], 0) / points.length,
  };
}

function assignmentFor(feature, data, country) {
  const center = gridCenter(feature);
  if (!center) return null;
  const key = `${country}:${feature.properties.cell_id}:${center.longitude.toFixed(6)}:${center.latitude.toFixed(6)}`;
  if (!GRID_LOOKUPS.has(key)) {
    GRID_LOOKUPS.set(key, lookupByCoords({ ...center, data }));
  }
  return GRID_LOOKUPS.get(key);
}

function quantile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * fraction))];
}

function ringCentre(geometry) {
  const ring = geometry?.type === "Polygon" ? geometry.coordinates[0] : geometry?.coordinates?.[0]?.[0];
  if (!ring?.length) return null;
  const pts = ring.slice(0, -1);
  return [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
}

/** Grid feature whose square contains [lon, lat] (areas too small to contain a grid-cell centre). */
function gridCellAt(gridLayer, centre) {
  if (!centre) return null;
  const [x, y] = centre;
  return gridLayer.features.find((f) => {
    const ring = f.geometry.coordinates[0];
    const xs = ring.map((p) => p[0]);
    const ys = ring.map((p) => p[1]);
    return x >= Math.min(...xs) && x < Math.max(...xs) && y >= Math.min(...ys) && y < Math.max(...ys);
  }) || null;
}

export async function buildAdminLayer(gridLayer, level, country = "RW") {
  if (country !== "RW" || level === "grid") return gridLayer;

  const data = await loadAdminData();
  const areas = sourceFeatures(data, level);
  const totals = new Map();
  let assignedGridCells = 0;

  for (const feature of gridLayer.features) {
    const hierarchy = assignmentFor(feature, data, country);
    const id = hierarchy?.ids?.[level];
    if (id == null) continue;

    const key = String(id);
    const entry = totals.get(key) || { sum: 0, count: 0, sourceCount: 0, sourceIds: [] };
    entry.sourceCount += 1;
    if (feature.properties.cell_id) entry.sourceIds.push(feature.properties.cell_id);
    const value = Number(feature.properties.value);
    if (feature.properties.value != null && Number.isFinite(value)) {
      entry.sum += value;
      entry.count += 1;
    }
    totals.set(key, entry);
    assignedGridCells += 1;
  }

  const features = areas.map((area) => {
    const props = area.properties;
    const id = String(props.__admin_id ?? props.Prov_ID ?? "");
    const name = props.__admin_name ?? props.Province;
    let entry = totals.get(id);
    const geometry = area.geometry;
    let centreFallback = false;
    if (!entry) {
      // No 5 km cell centre falls inside this (small) area: use the cell under the area's centre.
      const cell = gridCellAt(gridLayer, ringCentre(geometry));
      const value = Number(cell?.properties.value);
      if (cell) {
        const valued = cell.properties.value != null && Number.isFinite(value);
        entry = { sum: valued ? value : 0, count: valued ? 1 : 0, sourceCount: 1, sourceIds: [cell.properties.cell_id] };
        centreFallback = true;
      }
    }
    return {
      type: "Feature",
      geometry,
      properties: {
        admin_key: `${level}:${id}`,
        admin_id: id,
        admin_name: name,
        admin_level: level,
        value: entry?.count
          ? gridLayer.metadata.layer === "population_total" ? (centreFallback ? null : entry.sum) : entry.sum / entry.count
          : null,
        source_cell_count: entry?.sourceCount || 0,
        source_cell_ids: entry?.sourceIds || [],
        centre_fallback: centreFallback,
        area_km2: geometryArea(geometry),
      },
    };
  });
  const values = features.map((feature) => feature.properties.value).filter(Number.isFinite);
  const matchedFeatures = features.filter((feature) => feature.properties.source_cell_count > 0).length;

  return {
    ...gridLayer,
    features,
    metadata: {
      ...gridLayer.metadata,
      min: quantile(values, 0.02) ?? gridLayer.metadata.min,
      max: quantile(values, 0.98) ?? gridLayer.metadata.max,
      admin_level: level,
      n_missing: features.filter((feature) => feature.properties.value == null).length,
      boundary_source: "rwanda-location-lookup administrative GeoJSON",
      assigned_grid_cells: assignedGridCells,
      matched_admin_areas: matchedFeatures,
    },
  };
}

export function sumSelectedArea(features) {
  return features.reduce((sum, feature) => sum + (feature.properties.area_km2 || 0), 0);
}

export function boundsForAdminFeatures(features) {
  let minLongitude = Infinity;
  let minLatitude = Infinity;
  let maxLongitude = -Infinity;
  let maxLatitude = -Infinity;

  const visit = (coordinates) => {
    if (!Array.isArray(coordinates)) return;
    if (coordinates.length >= 2 && typeof coordinates[0] === "number") {
      minLongitude = Math.min(minLongitude, coordinates[0]);
      minLatitude = Math.min(minLatitude, coordinates[1]);
      maxLongitude = Math.max(maxLongitude, coordinates[0]);
      maxLatitude = Math.max(maxLatitude, coordinates[1]);
      return;
    }
    coordinates.forEach(visit);
  };

  features.forEach((feature) => visit(feature.geometry?.coordinates));
  if (!Number.isFinite(minLongitude)) return null;
  return [[minLatitude, minLongitude], [maxLatitude, maxLongitude]];
}

export function summarizeSelectedLayers(layerResults, selectedKeys) {
  return layerResults.map(({ catalog, layer }) => {
    const selected = layer.features.filter((feature) => selectedKeys.has(feature.properties.admin_key));
    const valued = selected.filter((feature) => Number.isFinite(feature.properties.value));
    const sourceCount = valued.reduce((sum, feature) => sum + feature.properties.source_cell_count, 0);
    const weightedSum = valued.reduce(
      (sum, feature) => sum + feature.properties.value * feature.properties.source_cell_count,
      0,
    );
    return {
      id: catalog.id,
      name: catalog.name,
      unit: catalog.unit,
      value: catalog.id === "population_total"
        ? valued.length
          ? selected.reduce((sum, feature) => sum + feature.properties.value, 0)
          : null
        : sourceCount ? weightedSum / sourceCount : null,
      matchedAreas: valued.length,
      sourceCells: sourceCount,
    };
  });
}