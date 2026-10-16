import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { fmtScore } from "../utils/format";
import AsyncView from "./AsyncView";

// Which indicator answers "what is the value of the active layer here?"
const LAYER_INDICATOR = {
  market_gap: "market_gap_score",
  population: "population_density",
  night_lights: "nighttime_radiance",
  grid: "distance_to_grid_km",
  survey_solar: "survey_solar_share",
  relative_wealth: "relative_wealth",
};
const KIND_ORDER = ["observed", "external_estimate", "derived", "model_prediction"];

function Badge({ kind, label }) {
  return <span className={`badge badge-${kind}`}>{label}</span>;
}

function Indicator({ item }) {
  return (
    <div className={`kv ${item.status === "missing" ? "missing" : ""}`}>
      <dt>{item.label}</dt>
      <dd>
        <span className="kv-value">{item.formatted}</span>
        <span className="kv-source">{item.source}{item.source_year ? ` · ${item.source_year}` : ""}</span>
      </dd>
    </div>
  );
}

export default function CellPanel({ cellId, threshold, layer, isSelected, onToggleSelect }) {
  const state = useApi(() => (cellId ? api.cell(cellId, threshold) : Promise.resolve(null)), [cellId, threshold]);

  if (!cellId) {
    return (
      <section className="panel cellpanel">
        <h2>Location details</h2>
        <p className="muted">Click an area on the map, or search for a district, sector, cell or coordinates.</p>
      </section>
    );
  }

  return (
    <section className="panel cellpanel" aria-live="polite">
      <AsyncView state={state} label="Loading cell..." isEmpty={(d) => !d || d.cell_id !== cellId} empty="Loading cell...">
        {(c) => {
          const highlighted = c.indicators.find((i) => i.key === LAYER_INDICATOR[layer]);
          const shown = c.indicators.filter((i) => i.kind !== "model_prediction" || c.model_status?.usable);
          const groups = KIND_ORDER.map((kind) => [kind, shown.filter((i) => i.kind === kind)]).filter(([, items]) => items.length);
          return (
            <>
              <div className="cell-head">
                <div>
                  <h2>{c.place_name ?? "Analysis area"}</h2>
                  <p className="cell-location">
                    {c.district ? `${c.district} District, ${c.province}` : "Centre outside Rwanda's district boundaries"}
                  </p>
                  <p className="hint">
                    5 km analysis area named after the administrative cell at its centre ({c.latitude.toFixed(4)}, {c.longitude.toFixed(4)}); it spans several villages.
                  </p>
                </div>
                <button className={isSelected ? "secondary" : "primary"} onClick={() => onToggleSelect({ key: c.cell_id, name: c.place_name ?? c.cell_id, level: "grid", cellIds: [c.cell_id] })}>
                  {isSelected ? "Remove from selection" : "Add to selection"}
                </button>
              </div>

              {highlighted && (
                <div className="highlight" aria-label={`${highlighted.label} for this cell`}>
                  <span className="highlight-label">{highlighted.label}</span>
                  <span className="highlight-value">{highlighted.formatted}</span>
                  <span className="highlight-meta">
                    {highlighted.kind_label} · {highlighted.source}{highlighted.source_year ? ` · ${highlighted.source_year}` : ""}
                    {highlighted.key === "population_density" && " · 5 km cell (~25 km²)"}
                  </span>
                  {highlighted.status === "missing" && <span className="highlight-meta">No value for this cell: {highlighted.description}</span>}
                </div>
              )}

              <div className={`score ${c.potentially_underserved ? "flag" : ""}`}>
                <div>
                  <span className="score-label">Market opportunity score</span>
                  <span className="score-value">{fmtScore(c.market_gap_score)}</span>
                </div>
                <span className={`evidence evidence-${c.evidence_level}`}>Evidence: {c.evidence_level}</span>
              </div>
              <p className="interpretation">{c.interpretation}</p>

              {c.drivers.some((d) => d.value != null) && (
                <ul className="drivers" aria-label="What drives the score">
                  {c.drivers.map((d) => (
                    <li key={d.factor} title={d.note}>
                      <span>{d.factor}</span>
                      <span className="bar-track"><span className="bar-fill" style={{ width: `${(d.value ?? 0) * 100}%` }} /></span>
                      <span className="bar-value">{d.value == null ? "n/a" : Math.round(d.value * 100)}</span>
                    </li>
                  ))}
                </ul>
              )}

              {groups.map(([kind, items]) => (
                <div key={kind} className="ind-group">
                  <Badge kind={kind} label={items[0].kind_label} />
                  <dl>{items.map((item) => <Indicator key={item.key} item={item} />)}</dl>
                </div>
              ))}
              {!c.model_status?.usable && (
                <p className="hint">Predicted solar penetration is not shown: {c.model_status?.reason}</p>
              )}
            </>
          );
        }}
      </AsyncView>
    </section>
  );
}
