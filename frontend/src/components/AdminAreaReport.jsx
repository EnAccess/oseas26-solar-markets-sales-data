import { useEffect, useState } from "react";
import { api } from "../services/api";
import { ADMIN_LEVELS, buildAdminLayer, summarizeSelectedLayers, sumSelectedArea } from "../utils/adminAreas";
import { fmtNum } from "../utils/format";

export default function AdminAreaReport({ adminLevel, availableLayers, layerData, selectedKeys, country }) {
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const selectionSignature = [...selectedKeys].sort().join("|");
  const selectedAreas = layerData?.features.filter((feature) => selectedKeys.has(feature.properties.admin_key)) || [];
  const selectedAreaKm2 = sumSelectedArea(selectedAreas);
  const sourceCells = selectedAreas.reduce((sum, feature) => sum + feature.properties.source_cell_count, 0);
  const levelName = ADMIN_LEVELS.find((level) => level.id === adminLevel)?.name || adminLevel;

  useEffect(() => {
    setReport(null);
    setError(null);
  }, [selectionSignature, adminLevel, country]);

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
        <ul className="admin-selection-list">
          {selectedAreas.map((feature) => (
            <li key={feature.properties.admin_key}>
              {feature.properties.admin_name}
              <small>{feature.properties.admin_id}</small>
            </li>
          ))}
        </ul>
      )}
      <button className="admin-report-generate" disabled={!selectedAreas.length || busy || !availableLayers.length} onClick={generateReport}>
        {busy ? "Generating report..." : "Generate report"}
      </button>
      {error && <p className="error-text" role="alert">{error}</p>}
      {report && (
        <div className="admin-report-output" id="admin-report-printable">
          <h3>{country} {levelName} report</h3>
          <p>{report.names.map((area) => area.name).join(", ")}</p>
          <p>{fmtNum(report.areaKm2, 2)} km² · {report.sourceCells} mapped grid cells</p>
          <small>Values use source grid-cell centers inside the selected polygons; small areas without a source center show no mapped data.</small>
          <table>
            <thead><tr><th>Dataset</th><th>Selected-area value</th><th>Cells</th></tr></thead>
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
          <small>
            {report.isDemo ? "Demo measurements; not real-world findings. " : "Measurements from the active API. "}
            Administrative polygon areas use bundled Rwanda boundary data. Generated {report.generatedAt}.
          </small>
          <button className="admin-report-print" onClick={() => window.print()}>Print report</button>
        </div>
      )}
    </section>
  );
}