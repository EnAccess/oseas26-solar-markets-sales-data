import { useCallback, useMemo, useState } from "react";

/**
 * Ordered, duplicate-free selection of map areas.
 * Each item: { key, name, level, cellIds } - cellIds are the 5 km grid cells used for reports.
 */
export function useSelection(limit = 500) {
  const [items, setItems] = useState([]);

  const toggle = useCallback((item) => {
    setItems((current) => (current.some((x) => x.key === item.key)
      ? current.filter((x) => x.key !== item.key)
      : current.length >= limit ? current : [...current, item]));
  }, [limit]);
  const add = useCallback((more) => {
    setItems((current) => {
      const keys = new Set(current.map((x) => x.key));
      const next = [...current];
      for (const item of more) {
        if (next.length >= limit) break;
        if (!keys.has(item.key)) { keys.add(item.key); next.push(item); }
      }
      return next;
    });
  }, [limit]);
  const remove = useCallback((key) => setItems((current) => current.filter((x) => x.key !== key)), []);
  const clear = useCallback(() => setItems([]), []);
  const keys = useMemo(() => items.map((x) => x.key), [items]);
  const cellIds = useMemo(() => [...new Set(items.flatMap((x) => x.cellIds))], [items]);

  return { items, keys, cellIds, has: (key) => keys.includes(key), toggle, add, remove, clear, limit };
}
