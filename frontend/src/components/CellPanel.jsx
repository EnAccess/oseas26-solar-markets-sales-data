import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { fmtInt, fmtNum, fmtPct } from "../utils/format";
import AsyncView from "./AsyncView";
import { lookup } from "rwanda-location-lookup";

const Row = ({ label, value, hint }) => (
  <div className="kv">
    <dt>{label}</dt>
    <dd>
      {value}
      {hint && <span className="hint"> ({hint})</span>}
    </dd>
  </div>
);

const fmtMaybePct = (v) => (v == null ? "Not available" : fmtPct(v));

export default function CellPanel({ cellId, threshold }) {
  const state = useApi(
    () => (cellId ? api.cell(cellId, threshold) : Promise.resolve(null)),
    [cellId, threshold],
  );
  const [location, setLocation] = useState(null);

  useEffect(() => {
    if (state.data?.latitude != null && state.data?.longitude != null) {
      lookup({ latitude: state.data.latitude, longitude: state.data.longitude })
        .then(setLocation)
        .catch(() => setLocation(null));
    } else {
      setLocation(null);
    }
  }, [state.data]);

  return (
    <aside className="panel cellpanel" aria-live="polite">
      <h2>Area details</h2>
      {!cellId ? (
        <p className="muted">Click a cell on the map to see its details.</p>
      ) : (
        <AsyncView
          state={state}
          label="Loading cell..."
          isEmpty={(d) => !d || d.cell_id !== cellId}
          empty="Loading cell..."
        >
          {(c) => (
            <>
              <p className="cell-id">
                {c.cell_id}
                {c.is_demo && " (demo data)"}
              </p>
              {location && (
                <p className="cell-location">
                  {location.cell && `${location.cell} Cell, `}
                  {location.district && `${location.district} District`}
                </p>
              )}
              <dl>
                <Row label="Population" value={fmtInt(c.population)} />
                <Row
                  label="Population density"
                  value={`${fmtNum(c.population_density, 0)} /km²`}
                />
                <Row
                  label="Relative wealth"
                  value={fmtNum(c.relative_wealth, 2)}
                  hint={
                    c.relative_wealth_observed === false
                      ? "imputed from national median"
                      : c.relative_wealth_observed === true
                        ? "observed"
                        : null
                  }
                />
                <Row
                  label="Predicted solar penetration"
                  value={fmtMaybePct(c.predicted_solar_penetration)}
                />
                {c.observed_solar_penetration != null && (
                  <Row
                    label="Survey-observed (this cell)"
                    value={fmtPct(c.observed_solar_penetration)}
                  />
                )}
                <Row
                  label="Potential market gap"
                  value={fmtMaybePct(c.market_gap_score)}
                />
                <Row
                  label="Distance to grid"
                  value={`${fmtNum(c.distance_to_grid_km, 1)} km`}
                />
                <Row
                  label="Solar resource"
                  value={`${fmtNum(c.solar_resource, 1)} kWh/m²/day`}
                />
                <Row
                  label="Nighttime radiance"
                  value={fmtNum(c.nighttime_radiance, 2)}
                />
              </dl>
              <div
                className={`interpretation ${
                  c.potentially_underserved ? "flag" : ""
                }`}
              >
                <strong>Interpretation</strong>
                <p>{c.interpretation}</p>
              </div>
            </>
          )}
        </AsyncView>
      )}
    </aside>
  );
}
