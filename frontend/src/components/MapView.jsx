import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import { PALETTES, rampColor, logNormalizer } from "../utils/colors";
import { fmtNum } from "../utils/format";
import NightLightsGlow from "./NightLightsGlow";

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], { padding: [8, 8] });
  }, [bounds, map]);
  return null;
}

export default function MapView({ layerData, infra, showInfra, bounds, center, zoom, opacity, threshold, selectedId, onSelect }) {
  const ref = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const meta = layerData?.metadata;
  const isGlow = meta?.layer === "night_lights";

  const style = useMemo(() => {
    if (!meta) return () => ({});
    const stops = PALETTES[meta.layer];
    const isLog = meta.layer === "night_lights";
    const norm = isLog
      ? logNormalizer(meta.min, meta.max)
      : (v) => (v - meta.min) / (meta.max - meta.min);

    return (f) => {
      const v = f.properties.value;
      const t = v == null ? null : norm(v);
      const faded = meta.layer === "market_gap" && v != null && v < threshold;
      const selected = f.properties.cell_id === selectedId;

      if (isGlow) {
        return {
          fillColor: "transparent",
          fillOpacity: 0.01,
          weight: selected ? 3 : 0,
          color: selected ? "#0f1b2e" : "transparent",
          opacity: selected ? 1 : 0,
        };
      }

      return {
        fillColor: rampColor(stops, t),
        fillOpacity: faded ? opacity * 0.2 : opacity,
        weight: selected ? 3 : 0.4,
        color: selected ? "#0f1b2e" : "#ffffff",
        opacity: selected ? 1 : 0.6,
      };
    };
  }, [meta, opacity, threshold, selectedId, isGlow]);

  useEffect(() => {
    ref.current?.setStyle(style);
  }, [style]);

  const onEachFeature = (feature, layer) => {
    const v = feature.properties.value;
    layer.bindTooltip(`${feature.properties.cell_id}: ${fmtNum(v, 2)}${meta && meta.unit !== "0-1" ? " " + meta.unit : ""}`, { sticky: true });
    layer.on({ click: () => onSelectRef.current(feature.properties.cell_id) });
  };

  const infraLines = useMemo(
    () => infra && { ...infra, features: infra.features.filter((f) => f.properties.kind === "grid_line") },
    [infra],
  );
  const minigrids = useMemo(() => (infra ? infra.features.filter((f) => f.properties.kind === "minigrid") : []), [infra]);

  return (
    <MapContainer center={center} zoom={zoom} className="map" scrollWheelZoom zoomSnap={0.25}>
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      <FitBounds bounds={bounds} />
      {isGlow && layerData && <NightLightsGlow data={layerData} opacity={opacity} />}
      {layerData && (
        <GeoJSON
          key={`${meta.layer}-${layerData.features.length}`}
          ref={ref}
          data={layerData}
          style={style}
          onEachFeature={onEachFeature}
        />
      )}
      {showInfra && infraLines && (
        <GeoJSON key="infra-lines" data={infraLines} style={{ color: "#0f1b2e", weight: 2, dashArray: "6 4" }} interactive={false} />
      )}
      {showInfra &&
        minigrids.map((f, i) => (
          <CircleMarker key={i} center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]} radius={6}
                        pathOptions={{ color: "#0f1b2e", fillColor: "#e0a526", fillOpacity: 1, weight: 2 }} />
        ))}
    </MapContainer>
  );
}