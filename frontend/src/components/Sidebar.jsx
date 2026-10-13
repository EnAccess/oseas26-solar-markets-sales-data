import { useState } from "react";
import { api, errorMessage } from "../services/api";
import { ADMIN_LEVELS } from "../utils/adminAreas";

export default function Sidebar({
  country, layers, layer, onLayer, opacity, onOpacity, threshold, onThreshold,
  showInfra, onShowInfra, clickSelects, onClickSelects, onLocation, adminLevel, onAdminLevel,
}) {
  const visible = layers.filter((l) => l.selector);
  const active = visible.find((l) => l.id === layer);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState(null);
  const [busy, setBusy] = useState(false);

  const find = async (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    try {
      const result = await api.searchLocation(query.trim(), country);
      setSearch(result);
      if (result.matched) onLocation(result, false);
    } catch (err) {
      setSearch({ matched: false, note: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="panel sidebar" aria-label="Map controls">
      <form className="field" onSubmit={find} role="search">
        <label htmlFor="loc-search">Find a location</label>
        <div className="input-row">
          <input id="loc-search" value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="District, sector, cell or -1.95, 30.06" />
          <button type="submit" disabled={busy}>{busy ? "…" : "Find"}</button>
        </div>
        {search && (
          <div className={`search-result ${search.matched ? "" : "warn"}`} role="status">
            {search.matched ? (
              <>
                <span>{search.name} · {search.cell_ids.length} analysis area{search.cell_ids.length === 1 ? "" : "s"}</span>
                <button type="button" className="link" onClick={() => onLocation(search, true)}>Add to selection</button>
              </>
            ) : search.note}
          </div>
        )}
      </form>

      <div className="field">
        <label htmlFor="admin-level">Show the map by</label>
        <select id="admin-level" value={adminLevel} onChange={(e) => onAdminLevel(e.target.value)} aria-describedby="level-help">
          {ADMIN_LEVELS.map((level) => <option key={level.id} value={level.id}>{level.name}</option>)}
        </select>
        <small id="level-help">
          {adminLevel === "grid"
            ? "Raw 5 km analysis cells used for the calculations."
            : "Official administrative boundaries. Values come from the 5 km analysis cells inside each area."}
        </small>
      </div>

      <fieldset className="field">
        <legend>Map layer</legend>
        {visible.map((l) => (
          <label key={l.id} className={`radio ${layer === l.id ? "active" : ""}`}>
            <input type="radio" name="layer" checked={layer === l.id} onChange={() => onLayer(l.id)} />
            <span>{l.name}</span>
          </label>
        ))}
        {active && <p className="layer-desc">{active.description}</p>}
      </fieldset>

      {layer === "market_gap" && (
        <label className="field">
          <span>Priority cut-off: {Math.round(threshold * 100)} / 100</span>
          <input type="range" min="0" max="1" step="0.01" value={threshold} onChange={(e) => onThreshold(+e.target.value)}
                 aria-describedby="cutoff-help" />
          <small id="cutoff-help">Cells below the cut-off are faded. The score ranks cells relative to the rest of Rwanda.</small>
        </label>
      )}

      <label className="field">
        <span>Layer opacity: {Math.round(opacity * 100)}%</span>
        <input type="range" min="0.2" max="1" step="0.05" value={opacity} onChange={(e) => onOpacity(+e.target.value)} />
      </label>

      <label className="check">
        <input type="checkbox" checked={showInfra} onChange={(e) => onShowInfra(e.target.checked)} />
        <span>Show mapped power lines, substations and plants</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={clickSelects} onChange={(e) => onClickSelects(e.target.checked)} />
        <span>Clicking an area adds or removes it from the selection</span>
      </label>
      <small className="muted">Tip: Ctrl/Cmd + click always toggles selection.</small>
    </aside>
  );
}
