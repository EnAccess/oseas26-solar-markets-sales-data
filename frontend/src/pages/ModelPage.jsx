import AsyncView from "../components/AsyncView";
import FeatureChart from "../components/FeatureChart";
import MetricsTable from "../components/MetricsTable";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { fmtInt, fmtNum } from "../utils/format";

const MODEL_NAMES = { random_forest: "Random Forest", xgboost: "XGBoost" };

function Gogla({ g }) {
  if (!g.available) return <p className="muted">{g.caveat}</p>;
  return (
    <div className="panel">
      <h3>National sanity check (GOGLA){g.is_demo && " - demo data"}</h3>
      <table>
        <tbody>
          {g.rows.map((r) => (
            <tr key={r.product_category}>
              <th scope="row">{r.product_category.replace(/_/g, " ")} ({r.year})</th>
              <td>{fmtInt(r.reported_sales)} units sold</td>
            </tr>
          ))}
          <tr><th scope="row">Model-estimated households with solar</th><td>{fmtInt(g.model_estimated_solar_households)}</td></tr>
          <tr><th scope="row">Ratio model / reported sales</th><td>{fmtNum(g.ratio_model_to_reported, 2)}</td></tr>
        </tbody>
      </table>
      <small className="muted">{g.caveat}</small>
    </div>
  );
}

export default function ModelPage({ country, meta }) {
  const perf = useApi(() => api.performance(country), [country]);
  const feats = useApi(() => api.features(country), [country]);
  const gogla = useApi(() => api.gogla(country), [country]);

  return (
    <div className="stack">
      <h2 className="page-title">Solar penetration model</h2>
      <p className={meta.model_status?.usable ? "callout" : "callout warn"}>
        {meta.model_status?.usable
          ? "Predictions from this model are used as solar uptake evidence in the market-gap score."
          : `Not used in the app. ${meta.model_status?.reason}`}
      </p>
      <AsyncView state={perf}>
        {(p) => (
          <>
            <p className={p.is_demo ? "callout warn" : "callout"}>{p.note}</p>
            <p className="muted">
              Selected model: <strong>{MODEL_NAMES[p.selected_model] ?? p.selected_model}</strong> ({p.selection_criterion}).
              Trained on {p.n_samples} labelled grid cells at {meta.grid_resolution_km} km resolution.
            </p>
            <div className="grid-2">
              <MetricsTable title="Random cross-validation" subtitle="Cells are split at random. Neighbouring cells can sit in both training and test sets, so this tends to be optimistic." m={p.random_cv} />
              <MetricsTable title="Spatial cross-validation" subtitle="Whole geographic blocks are held out, with a buffer, to mimic predicting in unsurveyed areas." m={p.spatial_cv} />
            </div>
            <div className="panel">
              <h3>Both models compared</h3>
              <table className="wide">
                <thead>
                  <tr><th>Model</th><th>Random R²</th><th>Random RMSE</th><th>Spatial R²</th><th>Spatial RMSE</th></tr>
                </thead>
                <tbody>
                  {Object.entries(p.models).map(([k, m]) => (
                    <tr key={k}>
                      <th scope="row">{MODEL_NAMES[k] ?? k}</th>
                      <td>{fmtNum(m.random_cv.r2, 3)}</td><td>{fmtNum(m.random_cv.rmse, 3)}</td>
                      <td>{fmtNum(m.spatial_cv.r2, 3)}</td><td>{fmtNum(m.spatial_cv.rmse, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </AsyncView>

      <AsyncView state={feats}>
        {(f) => (
          <div className="panel">
            <h3>{f.title}</h3>
            <p className="muted">Calculated from the fitted {MODEL_NAMES[f.selected_model] ?? f.selected_model} model.</p>
            <FeatureChart items={f.importance} />
            <p className="callout">{f.warning}</p>
          </div>
        )}
      </AsyncView>

      <AsyncView state={gogla}>{(g) => <Gogla g={g} />}</AsyncView>
    </div>
  );
}
