import { useEffect, useMemo, useRef } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  TileLayer,
  useMap,
} from "react-leaflet";
import { PALETTES, rampColor, logNormalizer } from "../utils/colors";
import { fmtNum } from "../utils/format";

function FitBounds({ bounds, selectionBounds, selectionZoom }) {
  const map = useMap();
  useEffect(() => {
    if (selectionBounds) {
      map.fitBounds(selectionBounds, { padding: [28, 28], maxZoom: selectionZoom });
      return;
    }
    if (bounds)
      map.fitBounds(
        [
          [bounds[1], bounds[0]],
          [bounds[3], bounds[2]],
        ],
        { padding: [8, 8] },
      );
  }, [bounds, map, selectionBounds, selectionZoom]);
  return null;
}

export default function MapView({
  layerData,
  infra,
  showInfra,
  bounds,
  selectionBounds,
  selectionZoom,
  center,
  zoom,
  opacity,
  threshold,
  selectedId,
  onSelect,
  adminLevel,
  selectedAreas,
  onToggleArea,
}) {
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
      const selected = f.properties.admin_key
        ? selectedAreas.has(f.properties.admin_key)
        : f.properties.cell_id === selectedId;

      if (isGlow) {
        return {
          // Render the measured cell values directly. A dark, opaque fill with
          // clear cell borders stays legible over the basemap at every zoom.
          fillColor: selected ? "#ffd166" : rampColor(stops, t),
          fillOpacity: selected ? 0.95 : Math.max(0.72, opacity),
          weight: selected ? 2 : 0.65,
          color: selected ? "#102a36" : "#fff7e8",
          opacity: selected ? 1 : 0.72,
        };
      }

      return {
        fillColor: selected ? "#ffd166" : rampColor(stops, t),
        fillOpacity: selected ? 0.88 : faded ? opacity * 0.2 : opacity,
        weight: selected ? 3 : 0.4,
        color: selected ? "#102a36" : "#ffffff",
        opacity: selected ? 1 : 0.6,
      };
    };
  }, [meta, opacity, threshold, selectedId, isGlow, selectedAreas]);

  useEffect(() => {
    ref.current?.setStyle(style);
  }, [style]);

  const onEachFeature = (feature, layer) => {
    const v = feature.properties.value;
    const areaProps = feature.properties;
    const label = areaProps.admin_name
      ? `${areaProps.admin_name} (${areaProps.admin_level})`
      : areaProps.cell_id;
    layer.bindTooltip(
      `${label}: ${fmtNum(v, 2)}${meta && meta.unit !== "0-1" ? " " + meta.unit : ""}`,
      { sticky: true, direction: "center", className: "admin-area-tooltip" },
    );
    layer.on({ click: () => {
      if (areaProps.admin_key) {
        onToggleArea(areaProps.admin_key);
        onSelectRef.current(areaProps.source_cell_ids?.[0] || null);
      } else {
        onSelectRef.current(areaProps.cell_id);
      }
    } });
  };

  const infraLines = useMemo(
    () =>
      infra && {
        ...infra,
        features: infra.features.filter(
          (f) => f.properties.kind === "grid_line",
        ),
      },
    [infra],
  );
  const minigrids = useMemo(
    () =>
      infra
        ? infra.features.filter((f) => f.properties.kind === "minigrid")
        : [],
    [infra],
  );

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className="map"
      scrollWheelZoom
      zoomSnap={0.25}
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      <FitBounds bounds={bounds} selectionBounds={selectionBounds} selectionZoom={selectionZoom} />
      {layerData && (
        <GeoJSON
          key={`${meta.layer}-${adminLevel}-${layerData.features.length}`}
          ref={ref}
          data={layerData}
          style={style}
          onEachFeature={onEachFeature}
        />
      )}
      {showInfra && infraLines && (
        <GeoJSON
          key="infra-lines"
          data={infraLines}
          style={{ color: "#0f1b2e", weight: 2, dashArray: "6 4" }}
          interactive={false}
        />
      )}
      {showInfra &&
        minigrids.map((f, i) => (
          <CircleMarker
            key={i}
            center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]}
            radius={6}
            pathOptions={{
              color: "#0f1b2e",
              fillColor: "#e0a526",
              fillOpacity: 1,
              weight: 2,
            }}
          />
        ))}
    </MapContainer>
  );
}
