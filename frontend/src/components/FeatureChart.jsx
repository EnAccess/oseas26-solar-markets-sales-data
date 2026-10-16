import { fmtPct } from "../utils/format";

export default function FeatureChart({ items }) {
  const max = Math.max(...items.map((i) => i.importance), 0.0001);
  return (
    <ul className="bars" aria-label="Model feature importance">
      {items.map((i) => (
        <li key={i.feature}>
          <span className="bar-label">{i.label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(i.importance / max) * 100}%` }} />
          </span>
          <span className="bar-value">{fmtPct(i.importance, 1)}</span>
        </li>
      ))}
    </ul>
  );
}
