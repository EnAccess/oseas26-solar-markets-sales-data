import AsyncView from "../components/AsyncView";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { fmtDate } from "../utils/format";

const STATUS = { real: "Loaded", missing: "Not available", synthetic: "Synthetic (demo)" };

export default function DataPage({ country, meta }) {
  const sources = useApi(() => api.dataSources(country), [country]);
  return (
    <div className="stack">
      <h2 className="page-title">Data sources</h2>
      <p className="muted">
        What is loaded in the current dataset (built {fmtDate(meta.built_at)}), what each source is used for, and what is
        missing. Unavailable sources are never replaced with invented values.
      </p>
      <AsyncView state={sources} isEmpty={(d) => !d.length} empty="No data sources are documented yet.">
        {(list) => (
          <div className="grid-2">
            {list.map((d) => (
              <article key={d.id} className={`panel source status-${d.status}`}>
                <div className="panel-head">
                  <h3>{d.name}</h3>
                  <span className={`badge badge-status-${d.status}`}>{STATUS[d.status] ?? d.status}</span>
                </div>
                <p>{d.description}</p>
                <dl>
                  <div className="kv"><dt>Used for</dt><dd>{d.role}</dd></div>
                  <div className="kv"><dt>Resolution</dt><dd>{d.resolution}</dd></div>
                  {d.date && <div className="kv"><dt>Date</dt><dd>{d.date}</dd></div>}
                  {d.retrieved_at && <div className="kv"><dt>Retrieved</dt><dd>{fmtDate(d.retrieved_at)}</dd></div>}
                  {d.licence && <div className="kv"><dt>Licence</dt><dd>{d.licence}</dd></div>}
                  {d.file && <div className="kv"><dt>File</dt><dd><code>{d.file}</code></dd></div>}
                  <div className="kv"><dt>Limitations</dt><dd>{d.limitations}</dd></div>
                  {d.note && <div className="kv"><dt>Note</dt><dd>{d.note}</dd></div>}
                </dl>
              </article>
            ))}
          </div>
        )}
      </AsyncView>
    </div>
  );
}
