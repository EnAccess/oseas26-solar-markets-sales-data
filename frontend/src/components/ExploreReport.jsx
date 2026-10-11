import { fmtNum } from "../utils/format";

function verdict(summary) {
  const dark = summary.darkCells;
  const total = summary.cellCount || 1;
  const share = dark / total;
  if (share >= 0.85) return { label: "Predominantly dark", tone: "dark" };
  if (share >= 0.5) return { label: "Mixed", tone: "mid" };
  return { label: "Predominantly lit", tone: "bright" };
}

export default function ExploreReport({ summary, meta, stats, onPrint, countryName }) {
  if (!summary || !meta) return null;

  const v = verdict(summary);
  const total = summary.cellCount || 1;
  const darkPct = ((summary.darkCells / total) * 100).toFixed(0);
  const midPct = ((summary.midCells / total) * 100).toFixed(0);
  const brightPct = ((summary.brightCells / total) * 100).toFixed(0);

  return (
    <div className="explore-report" id="explore-report-printable">
      <div className="report-header">
        <div className="report-kicker">Market-Reality Assessment</div>
        <div className="report-title">{summary.centerId}</div>
        <div className="report-sub">
          {countryName} · {meta.name} · {summary.radiusKm.toFixed(0)} km radius ·{" "}
          {new Date().toLocaleDateString()}
        </div>
      </div>

      <div className={`report-verdict verdict-${v.tone}`}>
        <div className="verdict-label">Nighttime signal</div>
        <div className="verdict-value">{v.label}</div>
        <div className="verdict-detail">
          {darkPct}% dark · {midPct}% mid · {brightPct}% bright across {summary.cellCount} cells
        </div>
      </div>

      <div className="report-section">1 · Satellite radiance (VIIRS)</div>
      <table className="report-table">
        <tbody>
          <tr><td className="k">Centre value</td><td className="v">{fmtNum(summary.centerValue, 3)} {meta.unit}</td></tr>
          <tr><td className="k">Mean over radius</td><td className="v">{fmtNum(summary.meanValue, 3)} {meta.unit}</td></tr>
          <tr><td className="k">Median over radius</td><td className="v">{fmtNum(summary.medianValue, 3)} {meta.unit}</td></tr>
          <tr><td className="k">90th percentile</td><td className="v">{fmtNum(summary.p90Value, 3)} {meta.unit}</td></tr>
          <tr><td className="k">Range</td><td className="v">{fmtNum(summary.minValue, 3)} – {fmtNum(summary.maxValue, 3)}</td></tr>
        </tbody>
      </table>

      <div className="report-callout">
        Darkness indicates the absence of a grid connection. It does <em>not</em>{" "}
        indicate the absence of off-grid solar: solar home systems are below the
        VIIRS detection floor and register as dark. Interpret this layer together
        with the penetration estimate below.
      </div>

      {stats && (
        <>
          <div className="report-section">2 · Model context (country)</div>
          <table className="report-table">
            <tbody>
              <tr><td className="k">Predicted penetration (country mean)</td><td className="v">{(stats.avg_predicted_penetration * 100).toFixed(1)} %</td></tr>
              <tr><td className="k">Potentially underserved cells</td><td className="v">{stats.potentially_underserved_cells} / {stats.n_cells}</td></tr>
              <tr><td className="k">Population in gap areas</td><td className="v">{fmtNum(stats.population_in_gap_areas, 0)}</td></tr>
              <tr><td className="k">Model R² — random CV</td><td className="v">{fmtNum(stats.model_r2_random, 3)}</td></tr>
              <tr><td className="k">Model R² — spatial block CV</td><td className="v">{fmtNum(stats.model_r2_spatial, 3)}</td></tr>
            </tbody>
          </table>
          <div className="report-callout">
            Random CV overstates performance under spatial autocorrelation. The
            spatial-block figure is the honest one. If the gap between them is
            large, treat cell-level predictions with caution.
          </div>
        </>
      )}

      <div className="report-section">3 · How to read this</div>
      <div className="report-body-text">
        This report describes the satellite and model context for a location.
        It does not, on its own, establish that the market has failed here. A
        dark cell may mean:
      </div>
      <ul className="report-list">
        <li><strong>No grid, no solar</strong> — a candidate for intervention.</li>
        <li><strong>No grid, solar present</strong> — market has already arrived, and the satellite cannot see it.</li>
        <li><strong>Grid present, unreliable</strong> — solar may be a complement rather than a substitute.</li>
      </ul>

      <div className="report-section">4 · Limitations</div>
      <div className="report-body-text">
        Distinguishing the three cases above requires survey-derived penetration
        estimates (DHS, MICS, ESMAP MTF) at cluster level. Where those labels are
        sparse, the model interpolates and may smooth over real variation. GOGLA
        sales data is national and semi-annual and cannot be resolved to a
        location. Do not use this report alone to allocate capital.
      </div>

      <div className="report-footer">
        Data: NASA VIIRS night-time radiance · Labels: DHS / MICS geo-clusters ·
        Model: spatial gradient boosting ·{" "}
        {stats?.is_demo ? "Demo data — not for operational decisions." : "Live data."}
      </div>

      <div className="report-actions">
        <button onClick={onPrint}>Print report</button>
      </div>
    </div>
  );
}