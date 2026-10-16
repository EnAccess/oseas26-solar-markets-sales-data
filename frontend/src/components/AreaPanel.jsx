import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { fmtInt, fmtLayerValue, fmtNum } from "../utils/format";
import AsyncView from "./AsyncView";

const LEVEL_NAMES = { province: "Province", district: "District", sector: "Sector", cell: "Cell", village: "Village" };

/** Details for an administrative area, summarised from the 5 km grid cells assigned to it. */
export default function AreaPanel({ area, layerMeta, country, threshold, isSelected, onToggleSelect, onOpenCell }) {
  const summary = useApi(
    () => (area.cellIds.length ? api.reportSummary(area.cellIds, threshold, country) : Promise.resolve(null)),
    [area.key, threshold, country],
  );

  return (
    <section className="panel cellpanel" aria-live="polite">
      <div className="cell-head">
        <div>
          <h2>{area.name}</h2>
          <p className="cell-location">{LEVEL_NAMES[area.level] ?? area.level} · official boundary</p>
        </div>
        <button className={isSelected ? "secondary" : "primary"} onClick={() => onToggleSelect(area)}>
          {isSelected ? "Remove from selection" : "Add to selection"}
        </button>
      </div>

      {layerMeta && (
        <div className="highlight" aria-label={`${layerMeta.name} for this area`}>
          <span className="highlight-label">{layerMeta.name}</span>
          <span className="highlight-value">{fmtLayerValue(area.value, layerMeta.unit)}</span>
          <span className="highlight-meta">
            {area.centreFallback
              ? "Area is smaller than one 5 km analysis cell: value of the cell under its centre."
              : `Average of ${area.cellIds.length} analysis cell${area.cellIds.length === 1 ? "" : "s"} whose centre lies in this area.`}
            {" "}{layerMeta.source}{layerMeta.source_date ? ` · ${layerMeta.source_date}` : ""}
          </span>
        </div>
      )}

      {!area.cellIds.length ? (
        <p className="muted">No 5 km analysis cell covers this area, so no indicators are available.</p>
      ) : (
        <AsyncView state={summary} label="Summarising area...">
          {(r) => r && (
            <>
              <dl>
                <div className="kv"><dt>Population (WorldPop 2020)</dt><dd><span className="kv-value">{area.centreFallback ? "Not estimated for areas smaller than a cell" : fmtInt(r.summary.population_total)}</span></dd></div>
                <div className="kv"><dt>Population density</dt><dd><span className="kv-value">{r.summary.population_density == null ? "–" : `${fmtInt(r.summary.population_density)} people/km²`}</span></dd></div>
                <div className="kv"><dt>Median nighttime radiance</dt><dd><span className="kv-value">{fmtNum(r.summary.median_radiance, 2)} nW/cm²/sr</span></dd></div>
                <div className="kv"><dt>Mean distance to mapped grid</dt><dd><span className="kv-value">{fmtNum(r.summary.mean_distance_to_grid_km, 1)} km</span></dd></div>
                <div className="kv"><dt>Opportunity score range</dt><dd><span className="kv-value">{r.summary.score_min == null ? "No score" : `${r.summary.score_min}–${r.summary.score_max} / 100`}</span></dd></div>
                {r.summary.districts.map((d) => (
                  <div className="kv" key={d.district}><dt>Solar ownership, {d.district} (survey)</dt>
                    <dd><span className="kv-value">{d.solar_share_pct == null ? "–" : `${d.solar_share_pct}% of households`}</span>
                      <span className="kv-source">district estimate, {d.sampled_solar_households ?? 0} sampled solar households</span></dd></div>
                ))}
              </dl>
              <h4>5 km analysis areas used</h4>
              <ul className="chips">
                {r.cells.map((c) => (
                  <li key={c.cell_id}><button className="chip" onClick={() => onOpenCell(c.cell_id, c.name)}>{c.name}</button></li>
                ))}
              </ul>
            </>
          )}
        </AsyncView>
      )}
    </section>
  );
}
