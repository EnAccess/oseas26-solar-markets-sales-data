import { useEffect, useState } from "react";
import { api, downloadBlob, errorMessage } from "../services/api";
import { fmtInt, fmtNum } from "../utils/format";

function ScoreBars({ cells, cutoff, median }) {
  const scored = cells.filter((c) => c.opportunity_score != null)
    .sort((a, b) => b.opportunity_score - a.opportunity_score).slice(0, 20);
  if (!scored.length) return <p className="muted">No selected cell has an opportunity score.</p>;
  return (
    <figure className="chart">
      <figcaption>Opportunity score by place (0–100, relative). Line: priority cut-off {cutoff}; Rwanda median {median}.</figcaption>
      <ul className="hbars" style={{ "--cutoff": `${cutoff}%` }}>
        {scored.map((c) => (
          <li key={c.cell_id}>
            <span className="hbar-label" title={c.name}>{c.name}</span>
            <span className="hbar-track">
              <span className={`hbar-fill ${c.flagged ? "flag" : ""}`} style={{ width: `${c.opportunity_score}%` }} />
              <span className="hbar-cutoff" aria-hidden="true" />
            </span>
            <span className="hbar-value">{c.opportunity_score}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

function ReportPreview({ report }) {
  const s = report.summary;
  return (
    <article className="report-preview" aria-label="Report preview">
      <h3>{report.title}</h3>
      <p className="muted">Generated {report.generated_at}</p>
      <div className="facts">
        <div><strong>{s.n_cells}</strong><span>cells · {fmtInt(s.area_km2)} km²</span></div>
        <div><strong>{fmtInt(s.population_total)}</strong><span>people (WorldPop 2020)</span></div>
        <div><strong>{fmtInt(s.population_density)}</strong><span>people/km²</span></div>
        <div><strong>{s.score_min == null ? "–" : `${s.score_min}–${s.score_max}`}</strong><span>opportunity score</span></div>
      </div>
      <h4>Key findings</h4>
      <ul className="findings">{report.interpretation.map((line) => <li key={line}>{line}</li>)}</ul>
      <ScoreBars cells={report.cells} cutoff={report.threshold_score} median={report.national.median} />
      <h4>Location indicators</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>Place (cell, sector)</th><th>District</th><th>Density /km²</th><th>Radiance nW/cm²/sr</th><th>Grid km</th><th>District solar %</th><th>Score</th></tr>
          </thead>
          <tbody>
            {report.cells.map((c) => (
              <tr key={c.cell_id}>
                <td>{c.name}</td>
                <td>{c.district ?? "–"}</td>
                <td>{fmtInt(c.indicators.population_density.value)}</td>
                <td>{fmtNum(c.indicators.nighttime_radiance.value, 2)}</td>
                <td>{fmtNum(c.indicators.distance_to_grid_km.value, 1)}</td>
                <td>{c.indicators.survey_solar_share.display_value ?? "–"}</td>
                <td>{c.opportunity_score ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">{report.method.interpretation}</p>
    </article>
  );
}

export default function SelectionPanel({ country, items, limit, threshold, onRemove, onClear, onFocus }) {
  const ids = [...new Set(items.map((x) => x.cellIds).flat())];
  const title = items.length
    ? `Solar market reality: ${items.map((x) => x.name).join(", ")}`.slice(0, 120)
    : null;
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const signature = ids.join("|");

  useEffect(() => { setReport(null); setError(null); }, [signature, threshold]);

  const generate = async () => {
    setBusy("summary");
    setError(null);
    try {
      setReport(await api.reportSummary(ids, threshold, country, title));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const download = async (format) => {
    setBusy(format);
    setError(null);
    try {
      const blob = await api.reportFile(format, ids, threshold, country, title);
      downloadBlob(blob, `solar-market-report-${ids.length}-cells.${format}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel selection" aria-live="polite">
      <div className="panel-head">
        <h2>Selection <span className="count">{items.length}</span></h2>
        {items.length > 0 && <button className="link" onClick={onClear}>Clear all</button>}
      </div>
      {!items.length ? (
        <p className="muted">
          Nothing selected. Use “Add to selection” in the details panel, Ctrl/Cmd + click on the map,
          or search for a district and add it.
        </p>
      ) : (
        <>
          <ul className="chips" aria-label="Selected areas">
            {items.map((item) => (
              <li key={item.key}>
                <button className="chip" onClick={() => onFocus(item)}>{item.name}</button>
                <button className="chip-remove" aria-label={`Remove ${item.name}`} onClick={() => onRemove(item.key)}>×</button>
              </li>
            ))}
          </ul>
          <p className="hint">{ids.length} analysis cell{ids.length === 1 ? "" : "s"} (5 km) cover the selected areas; the report uses their data.</p>
          {(items.length >= limit || ids.length > 500) && <p className="hint">Reports are limited to 500 analysis cells.</p>}
          <div className="actions">
            <button className="primary" onClick={generate} disabled={busy != null}>
              {busy === "summary" ? "Generating report..." : "Generate report"}
            </button>
            <button className="secondary" onClick={() => download("pdf")} disabled={busy != null}>
              {busy === "pdf" ? "Preparing PDF..." : "Download PDF"}
            </button>
            <button className="secondary" onClick={() => download("csv")} disabled={busy != null}>
              {busy === "csv" ? "Preparing CSV..." : "CSV"}
            </button>
          </div>
        </>
      )}
      {error && <p className="error-text" role="alert">{error}</p>}
      {report && <ReportPreview report={report} />}
    </section>
  );
}
