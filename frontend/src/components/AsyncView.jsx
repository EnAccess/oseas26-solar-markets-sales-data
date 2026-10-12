/** Renders loading / error / empty states around async data (from useApi). */
export function Loading({ label = "Loading..." }) {
  return (
    <div className="state state-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorBox({ message }) {
  return (
    <div className="state state-error" role="alert">
      {message}
    </div>
  );
}

export function EmptyBox({ children }) {
  return <div className="state state-empty">{children}</div>;
}

export default function AsyncView({ state, children, isEmpty, empty, label }) {
  if (state.status === "loading") return <Loading label={label} />;
  if (state.status === "error") return <ErrorBox message={state.error} />;
  if (isEmpty?.(state.data)) return <EmptyBox>{empty}</EmptyBox>;
  return children(state.data);
}
