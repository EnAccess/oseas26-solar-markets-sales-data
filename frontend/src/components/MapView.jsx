import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { PALETTES, normalizer, rampColor } from "../utils/colors";
import { fmtLayerValue } from "../utils/format";

const SELECTED = "#84cc16";
const FOCUSED = "#064e3b";
const LINE_STYLE = {
  line: { color: "#0f172a", weight: 2.4, opacity: 0.9 },
  cable: { color: "#334155", weight: 1.6, dashArray: "2 4", opacity: 0.9 },
  minor_line: { color: "#334155", weight: 1.4, dashArray: "6 4", opacity: 0.85 },
};

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], { padding: [8, 8] });
  }, [bounds, map]);
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.fitBounds(target, { padding: [40, 40], maxZoom: 11 });
  }, [target, map]);
  return null;
}

function infraLabel(p) {
  const name = p.name ? `${p.name} · ` : "";
  const kv = p.voltage ? ` · ${String(p.voltage).split(";").map((v) => `${Math.round(+v / 1000)} kV`).join("/")}` : "";
  return `${name}${(p.line_class || p.kind || "").replace("_", " ")}${kv} (OpenStreetMap)`;
}

export default function MapView({
  layerData, infra, showInfra, bounds, flyTo, center, zoom, opacity, threshold,
  focusedKey, selectedKeys, onAreaClick, adminLevel,
}) {
  const ref = useRef(null);
  const clickRef = useRef(onAreaClick);
  clickRef.current = onAreaClick;
  const meta = layerData?.metadata;
  const selected = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const keyOf = (props) => props.admin_key ?? props.cell_id;

  const style = useMemo(() => {
    if (!meta) return () => ({});
    const stops = PALETTES[meta.layer];
    const norm = normalizer(meta);
    const cutoff = threshold * 100;
    return (f) => {
      const v = f.properties.value;
      const isFocused = keyOf(f.properties) === focusedKey;
      const isSelected = selected.has(keyOf(f.properties));
      const faded = meta.layer === "market_gap" && v != null && v < cutoff;
      return {
        fillColor: rampColor(stops, v == null ? null : norm(v)),
        fillOpacity: faded ? opacity * 0.35 : opacity,
        weight: isFocused ? 3 : isSelected ? 2.5 : f.properties.admin_key ? 0.8 : 0.35,
        color: isFocused ? FOCUSED : isSelected ? SELECTED : f.properties.admin_key ? "#064e3b" : "#ffffff",
        opacity: isFocused || isSelected ? 1 : f.properties.admin_key ? 0.45 : 0.7,
      };
    };
  }, [meta, opacity, threshold, focusedKey, selected]);

  useEffect(() => {
    ref.current?.setStyle(style);
    ref.current?.eachLayer((layer) => {
      const key = layer.feature && keyOf(layer.feature.properties);
      if (key === focusedKey || selected.has(key)) layer.bringToFront();
    });
  }, [style, focusedKey, selected]);

  const onEachFeature = (feature, layer) => {
    const p = feature.properties;
    const label = p.admin_name ? `${p.admin_name} (${p.admin_level})` : p.name ?? "Analysis area";
    layer.bindTooltip(`${label}: ${fmtLayerValue(p.value, meta?.unit)}`, { sticky: true, className: "cell-tooltip" });
    layer.on({ click: (e) => clickRef.current(p, e.originalEvent) });
  };

  const lines = useMemo(() => infra && {
    type: "FeatureCollection",
    features: infra.features.filter((f) => f.properties.kind === "grid_line"),
  }, [infra]);
  const points = useMemo(() => (infra ? infra.features.filter((f) => f.geometry?.type === "Point") : []), [infra]);

  return (
    <MapContainer center={center} zoom={zoom} className="map" scrollWheelZoom zoomSnap={0.25}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
      <FitBounds bounds={bounds} />
      <FlyTo target={flyTo} />
      {layerData && (
        <GeoJSON key={`${meta.layer}-${adminLevel}-${layerData.features.length}`} ref={ref} data={layerData} style={style} onEachFeature={onEachFeature} />
      )}
      {showInfra && lines && (
        <GeoJSON
          key={`infra-${lines.features.length}`}
          data={lines}
          style={(f) => LINE_STYLE[f.properties.line_class] || LINE_STYLE.line}
          onEachFeature={(f, layer) => layer.bindTooltip(infraLabel(f.properties), { sticky: true })}
        />
      )}
      {showInfra && points.map((f) => (
        <CircleMarker
          key={f.properties.osm_id || f.geometry.coordinates.join(",")}
          center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
          radius={f.properties.kind === "plant" ? 6 : 4}
          pathOptions={{
            color: "#0f172a", weight: 1.5, fillOpacity: 1,
            fillColor: f.properties.kind === "plant" ? "#f59e0b" : f.properties.kind === "minigrid" ? SELECTED : "#ffffff",
          }}
        >
          <Tooltip>{infraLabel(f.properties)}</Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
