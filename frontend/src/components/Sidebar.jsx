import { fmtPct } from "../utils/format";
import { ADMIN_LEVELS } from "../utils/adminAreas";

export default function Sidebar({
  countries, country, onCountry, layers, layer, onLayer,
  opacity, onOpacity, threshold, onThreshold, showInfra, onShowInfra,
  adminLevel, onAdminLevel,
}) {
  return (
    <aside className="panel sidebar" aria-label="Filters">
      <h2>Filters</h2>

      <label className="field">
        <span>Country</span>
        <select value={country} onChange={(e) => onCountry(e.target.value)}>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>{c.name}</option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Administrative boundary</span>
        <select value={adminLevel} onChange={(event) => onAdminLevel(event.target.value)}>
          {ADMIN_LEVELS.map((level) => (
            <option key={level.id} value={level.id}>{level.name}</option>
          ))}
        </select>
      </label>

      <fieldset className="field">
        <legend>Layer</legend>
        {layers.map((l) => (
          <label key={l.id} className={`radio ${layer === l.id ? "active" : ""}`}>
            <input type="radio" name="layer" checked={layer === l.id} onChange={() => onLayer(l.id)} />
            <span>{l.name}</span>
          </label>
        ))}
      </fieldset>

      <label className="field">
        <span>Gap threshold: {fmtPct(threshold)}</span>
        <input type="range" min="0" max="1" step="0.01" value={threshold}
               onChange={(e) => onThreshold(+e.target.value)} />
        <small>Cells with a Potential Market Gap at or above this value count as potentially underserved. Cells below it are faded on the gap layer.</small>
      </label>

      <label className="field">
        <span>Opacity: {Math.round(opacity * 100)}%</span>
        <input type="range" min="0.2" max="1" step="0.05" value={opacity}
               onChange={(e) => onOpacity(+e.target.value)} />
      </label>

      <label className="check">
        <input type="checkbox" checked={showInfra} onChange={(e) => onShowInfra(e.target.checked)} />
        <span>Show grid lines and minigrids</span>
      </label>
    </aside>
  );
}
