import { Link } from "react-router-dom";
import { fmtDate } from "../utils/format";

const EVIDENCE = [
  ["Observed", "badge-observed", "Direct measurements: NASA VNP46A2 nighttime radiance, MTF household survey responses, mapped OpenStreetMap power lines."],
  ["External modelled estimate", "badge-external_estimate", "Other organisations' models: WorldPop 2020 population, Meta Relative Wealth Index."],
  ["Derived in this tool", "badge-derived", "Calculated here from the inputs above: distance to grid, district solar share, energy need, market opportunity score."],
  ["Model prediction", "badge-model_prediction", "This project's trained model. Shown only when it was trained on real, georeferenced survey labels."],
];

export default function AboutPage({ meta }) {
  const m = meta.method || {};
  return (
    <div className="stack narrow prose">
      <h2 className="page-title">About Solar Market Reality</h2>
      <p className="lead">
        Solar Market Reality is a market-reality layer for the{" "}
        <a href="https://www.energyaccessexplorer.org" target="_blank" rel="noreferrer">Energy Access Explorer</a>. It helps
        planners and funders in Rwanda separate places where the off-grid solar market has not arrived from places where it
        has quietly succeeded, and flags where the evidence is too thin to tell.
      </p>

      <h3>The problem</h3>
      <p>
        Satellite night-light sensors have a detection floor well above the light from a solar home system or lantern. A village
        where every household owns solar and a village with no energy access both look dark. Reading "dense and dark" as
        "underserved" therefore points capital at the places where the off-grid sector has already done its best work.
        Darkness marks the absence of grid electricity, the addressable market, but says nothing about whether that market
        has been served. Penetration has to come from sources that measure it: household surveys.
      </p>

      <h3>How the Potential Market Gap works</h3>
      <ol>
        <li><strong>Energy need</strong> (0–100): {m.energy_need}. Darkness carries the smallest weight because it largely repeats the distance-to-grid signal.</li>
        <li><strong>Solar uptake evidence</strong>: {m.solar_uptake}.</li>
        <li><strong>Market opportunity score</strong>: <code>{m.formula}</code>, shown as 0–100.</li>
      </ol>
      <p>
        {m.interpretation} A cell with no uptake evidence gets <em>no</em> score rather than a high one: missing evidence is not
        evidence of an underserved market. The priority cut-off (default {Math.round(meta.underserved_threshold * 100)}/100)
        is a relative threshold you can change on the map.
      </p>

      <h3>Observed data, estimates, model predictions and scores</h3>
      <ul className="evidence-key">
        {EVIDENCE.map(([label, cls, text]) => (
          <li key={label}><span className={`badge ${cls}`}>{label}</span> {text}</li>
        ))}
      </ul>
      <p>
        Model status: {meta.model_status?.reason} The repository contains no georeferenced (GPS) survey clusters, so predicted
        penetration is currently not used anywhere in the app.
      </p>

      <h3>Principal data and indicators</h3>
      <ul>
        <li>Population and density: WorldPop 2020, 1 km, summed to 5 km cells (people/km²).</li>
        <li>Nighttime radiance: NASA Black Marble VNP46A2 (nW/cm²/sr), a grid-electricity proxy only.</li>
        <li>Electricity infrastructure: OpenStreetMap power lines, substations and plants; distance to the nearest mapped line.</li>
        <li>Solar ownership: Multi-Tier Framework household survey, solar device module, as district estimates.</li>
        <li>Relative wealth: Meta Relative Wealth Index, shown for context; it is not part of the score.</li>
      </ul>
      <p>See <Link to="/data">Data sources</Link> for dates, licences and files. This dataset was built on {fmtDate(meta.built_at)}.</p>

      <h3>How to interpret results</h3>
      <ul>
        <li>Use the score to decide where to look first, not where to invest. It is not a share of households and not a market size.</li>
        <li>Survey evidence is district-wide and based on small samples, so cells in the same district share one uptake value.</li>
        <li>A mapped power line does not mean households are connected, and OpenStreetMap coverage is incomplete.</li>
        <li>Confirm results in the field and against distributor sales and results-based-financing connection records.</li>
      </ul>
      <p>Full list: <Link to="/limitations">Limitations</Link>.</p>
    </div>
  );
}
