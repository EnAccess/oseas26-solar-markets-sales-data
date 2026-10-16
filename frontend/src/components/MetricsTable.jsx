import { fmtNum } from "../utils/format";

export default function MetricsTable({ title, subtitle, m }) {
  return (
    <div className="panel metrics">
      <h3>{title}</h3>
      <p className="muted">{subtitle}</p>
      <table>
        <tbody>
          <tr><th scope="row">MAE</th><td>{fmtNum(m.mae, 3)}</td></tr>
          <tr><th scope="row">RMSE</th><td>{fmtNum(m.rmse, 3)}</td></tr>
          <tr><th scope="row">R²</th><td>{fmtNum(m.r2, 3)}</td></tr>
        </tbody>
      </table>
      <small className="muted">
        {m.n_evaluated} labelled cells, {m.n_folds} folds
        {m.n_blocks ? `, ${m.n_blocks} blocks of ${m.block_km} km, ${m.buffer_km} km buffer` : ""}
      </small>
    </div>
  );
}
