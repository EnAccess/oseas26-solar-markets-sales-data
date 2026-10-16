import { useEffect, useState } from "react";
import { errorMessage } from "../services/api";

/** Runs `fn` whenever `deps` change. Returns { status: 'loading'|'done'|'error', data, error }. */
export function useApi(fn, deps) {
  const [state, setState] = useState({ status: "loading" });
  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    Promise.resolve(fn())
      .then((data) => !cancelled && setState({ status: "done", data }))
      .catch((err) => !cancelled && setState({ status: "error", error: errorMessage(err) }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
