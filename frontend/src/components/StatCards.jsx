import { fmtCompact, fmtInt } from "../utils/format";

function Card({ label, value, sub }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export default function StatCards({ s }) {
  return (
    <section className="stats" aria-label="Country summary">
      <Card label="Cells at or above the cut-off" value={fmtInt(s.potentially_underserved_cells)}
            sub={`of ${fmtInt(s.n_scored_cells)} scored cells (cut-off ${Math.round(s.threshold * 100)}/100)`} />
      <Card label="People in those cells" value={fmtCompact(s.population_in_gap_areas)}
            sub={`of ${fmtCompact(s.total_population)} (WorldPop 2020)`} />
      <Card label="Cells without a score" value={fmtInt(s.n_cells - s.n_scored_cells)}
            sub="missing population or solar uptake evidence" />
      <Card label="Area covered" value={`${fmtInt(s.total_area_km2)} km²`} sub={`${fmtInt(s.n_cells)} cells of 5 km`} />
    </section>
  );
}
