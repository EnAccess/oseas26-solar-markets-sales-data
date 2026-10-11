import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../services/api";
import { ADMIN_LEVELS, buildAdminLayer, summarizeSelectedLayers, sumSelectedArea } from "../utils/adminAreas";
import { fmtNum } from "../utils/format";

const MAP_WIDTH = 720;
const MAP_HEIGHT = 300;
const MAP_PADDING = 18;

function geometryPolygons(geometry) {
  if (geometry?.type === "Polygon") return [geometry.coordinates];
  if (geometry?.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

function geometryPositions(geometry) {
  return geometryPolygons(geometry).flat(2);
}

function SelectionMap({ areas }) {
  const positions = areas.flatMap((feature) => geometryPositions(feature.geometry));
  if (!positions.length) return null;

  const bounds = positions.reduce((current, position) => ({
    minLongitude: Math.min(current.minLongitude, position[0]),
    maxLongitude: Math.max(current.maxLongitude, position[0]),
    minLatitude: Math.min(current.minLatitude, position[1]),
    maxLatitude: Math.max(current.maxLatitude, position[1]),
  }), {
    minLongitude: Infinity,
    maxLongitude: -Infinity,
    minLatitude: Infinity,
    maxLatitude: -Infinity,
  });
  const { minLongitude, maxLongitude, minLatitude, maxLatitude } = bounds;
  const latitudeFactor = Math.cos(((minLatitude + maxLatitude) / 2) * Math.PI / 180);
  const geographicWidth = Math.max((maxLongitude - minLongitude) * latitudeFactor, 1e-8);
  const geographicHeight = Math.max(maxLatitude - minLatitude, 1e-8);
  const scale = Math.min(
    (MAP_WIDTH - MAP_PADDING * 2) / geographicWidth,
    (MAP_HEIGHT - MAP_PADDING * 2) / geographicHeight,
  );
  const drawnWidth = geographicWidth * scale;
  const drawnHeight = geographicHeight * scale;
  const offsetX = (MAP_WIDTH - drawnWidth) / 2;
  const offsetY = (MAP_HEIGHT - drawnHeight) / 2;
  const project = ([longitude, latitude]) => [
    offsetX + (longitude - minLongitude) * latitudeFactor * scale,
    offsetY + (maxLatitude - latitude) * scale,
  ];
  const names = areas.map((feature) => feature.properties.admin_name).join(", ");

  return (
    <figure className="admin-report-map">
      <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label={`Selected area map: ${names}`}>
        <rect width={MAP_WIDTH} height={MAP_HEIGHT} rx="4" fill="#edf2f1" />
        {areas.map((feature) => (
          <g key={feature.properties.admin_key}>
            {geometryPolygons(feature.geometry).map((polygon, polygonIndex) => {
              const path = polygon.map((ring) => {
                const projected = ring.map(project);
                return `M${projected.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join("L")}Z`;
              }).join("");
              return (
                <path
                  key={`${feature.properties.admin_key}-${polygonIndex}`}
                  d={path}
                  fill="#f0bd4f"
                  fillRule="evenodd"
                  stroke="#174f58"
                  strokeWidth="1.4"
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
          </g>
        ))}
      </svg>
      <figcaption>{names}</figcaption>
    </figure>
  );
}

function ReportDocument({ report, country, levelName, mappedDatasets, onPrint }) {
  return (
    <article className="admin-report-output">
      <header className="admin-report-header">
        <p className="admin-report-kicker">Rwanda · {levelName} coverage</p>
        <h3>Selected-area report</h3>
        <p className="admin-report-area-names">{report.names.map((area) => area.name).join(", ")}</p>
        <p className="admin-report-generated">Generated {report.generatedAt}</p>
      </header>

      <div className="admin-report-facts">
        <div><strong>{fmtNum(report.areaKm2, 1)}</strong><span>km² selected</span></div>
        <div><strong>{report.names.length}</strong><span>{levelName.toLowerCase()}{report.names.length === 1 ? "" : "s"}</span></div>
        <div><strong>{report.sourceCells}</strong><span>mapped grid cells</span></div>
        <div><strong>{mappedDatasets}/{report.layers.length}</strong><span>datasets with values</span></div>
      </div>

      <section className="admin-report-section">
        <h4>Selected coverage map</h4>
        <SelectionMap areas={report.areas} />
      </section>

      <section className="admin-report-section">
        <h4>Selected administrative areas</h4>
        <ul className="admin-report-area-list">
          {report.names.map((area) => (
            <li key={area.id}><span>{area.name}</span><small>ID {area.id}</small></li>
          ))}
        </ul>
      </section>

      <section className="admin-report-section">
        <h4>Measurements within selected coverage</h4>
        <table>
          <thead><tr><th>Dataset</th><th>Selected-area value</th><th>Mapped cells</th></tr></thead>
          <tbody>
            {report.layers.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td>{row.value == null ? "No mapped data" : `${fmtNum(row.value, row.id === "population_total" ? 0 : 3)} ${row.unit}`}</td>
                <td>{row.sourceCells}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer className="admin-report-footer">
        <p>{report.isDemo ? "Demo measurements; not real-world findings." : "Measurements from the active API."}</p>
        <p>Values use source grid-cell centers inside selected polygons. Small areas without a source center have no mapped data.</p>
      </footer>
      {onPrint && <button className="admin-report-print" onClick={onPrint}>Print this report</button>}
    </article>
  );
}

export default function AdminAreaReport({ adminLevel, availableLayers, layerData, selectedKeys, selectedFeatures, country, onClearSelection }) {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const selectionSignature = [...selectedKeys].sort().join("|");
  const selectedAreas = layerData?.features.filter((feature) => selectedKeys.has(feature.properties.admin_key)) || [];
  const selectedAreaKm2 = sumSelectedArea(selectedAreas);
  const sourceCells = selectedAreas.reduce((sum, feature) => sum + feature.properties.source_cell_count, 0);
  const mappedDatasets = report?.layers.filter((row) => row.value != null).length || 0;
  const levelName = ADMIN_LEVELS.find((level) => level.id === adminLevel)?.name || adminLevel;

  useEffect(() => {
    setReport(null);
    setError(null);
  }, [selectionSignature, adminLevel, country]);

  const printReport = () => {
    window.print();
  };

  const generateReport = async () => {
    setBusy(true);
    setError(null);
    try {
      const layerResults = await Promise.all(availableLayers.map(async (catalog) => {
        const source = await api.layer(catalog.id, country);
        const layer = await buildAdminLayer(source, adminLevel, country);
        return { catalog, layer };
      }));
      setReport({
        layers: summarizeSelectedLayers(layerResults, selectedKeys),
        names: selectedAreas.map((feature) => ({
          name: feature.properties.admin_name,
          id: feature.properties.admin_id,
        })),
        areas: selectedFeatures,
        areaKm2: selectedAreaKm2,
        sourceCells,
        isDemo: layerData?.metadata?.is_demo ?? true,
        generatedAt: new Date().toLocaleString(),
      });
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : requestError.message || "Could not generate this report.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel admin-report" aria-live="polite">
      <h2>Selected area report</h2>
      <p className="muted">
        {selectedAreas.length} {levelName.toLowerCase()}{selectedAreas.length === 1 ? "" : "s"}
        {selectedAreas.length > 0 && ` · ${fmtNum(selectedAreaKm2, 1)} km² · ${sourceCells} mapped grid cells`}
      </p>
      {selectedAreas.length > 0 && (
        <>
          <section className="admin-selection-map" aria-label="Selected area map view">
            <h3>Selected coverage</h3>
            <SelectionMap areas={selectedAreas} />
          </section>
          <ul className="admin-selection-list">
            {selectedAreas.map((feature) => (
              <li key={feature.properties.admin_key}>
                <span>{feature.properties.admin_name}</span>
                <small>{feature.properties.admin_id}</small>
              </li>
            ))}
          </ul>
          <button className="admin-report-clear" onClick={onClearSelection}>Clear selection</button>
        </>
      )}
      <button className="admin-report-generate" disabled={!selectedAreas.length || busy || !availableLayers.length} onClick={generateReport}>
        {busy ? "Building report..." : "Generate selected-area report"}
      </button>
      {error && <p className="error-text" role="alert">{error}</p>}
      {report && (
        <>
          <ReportDocument
            report={report}
            country={country}
            levelName={levelName}
            mappedDatasets={mappedDatasets}
            onPrint={printReport}
          />
          {createPortal(
            <div className="admin-report-print-root" aria-hidden="true">
              <ReportDocument report={report} country={country} levelName={levelName} mappedDatasets={mappedDatasets} />
            </div>,
            document.body,
          )}
        </>
      )}
    </section>
  );
}