import AsyncView from "../components/AsyncView";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";

export default function LimitationsPage() {
  const state = useApi(() => api.limitations(), []);
  return (
    <div className="stack narrow">
      <h2 className="page-title">Limitations</h2>
      <p>
        Results describe <strong>potentially underserved off-grid solar areas</strong> that need further
        investigation. They do not show that an area is commercially viable.
      </p>
      <AsyncView state={state} isEmpty={(d) => !d.length} empty="No limitations documented.">
        {(items) => (
          <ul className="limits">
            {items.map((t) => <li key={t}>{t}</li>)}
          </ul>
        )}
      </AsyncView>
    </div>
  );
}
