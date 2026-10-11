import { useState } from "react";
import { summarizeNeighborhood, findById } from "../utils/explore";
import ExploreReport from "./ExploreReport";

export default function ExploreAssistant({ layerData, stats, meta, selectedId, onJumpToCell, country, countryName }) {
  const [open, setOpen] = useState(false);
  const [radius, setRadius] = useState(15);
  const [query, setQuery] = useState("");
  const [error, setError] = useState(null);

  const features = layerData?.features || [];
  const selected = selectedId ? features.find((f) => f.properties.cell_id === selectedId) : null;
  const summary = selected ? summarizeNeighborhood(features, selected, radius, stats) : null;

  const handleSearch = () => {
    setError(null);
    const found = findById(features, query);
    if (!found) {
      setError(`No cell matching "${query}".`);
      return;
    }
    onJumpToCell(found.properties.cell_id);
    setQuery("");
  };

  const handlePrint = () => {
    const w = window.open("", "_blank", "width=800,height=1000");
    const node = document.getElementById("explore-report-printable");
    if (!w || !node) return;
    w.document.write(`
      <html>
        <head>
          <title>Market-Reality Assessment</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 40px; color: #111; max-width: 720px; margin: 0 auto; }
            .report-kicker { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: #666; }
            .report-title { font-size: 24px; font-weight: 700; margin: 2px 0; }
            .report-sub { font-size: 12px; color: #555; margin-bottom: 20px; }
            .report-verdict { padding: 14px; border-radius: 8px; margin: 16px 0; background: #f5f5f5; border-left: 4px solid #888; }
            .verdict-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #666; }
            .verdict-value { font-size: 18px; font-weight: 700; margin: 4px 0; }
            .verdict-detail { font-size: 12px; color: #555; }
            .report-section { font-weight: 600; margin: 24px 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #555; }
            .report-table { width: 100%; border-collapse: collapse; }
            .report-table td { padding: 6px 0; border-bottom: 1px solid #eee; font-size: 13px; }
            .report-table .k { color: #555; width: 60%; }
            .report-table .v { text-align: right; font-variant-numeric: tabular-nums; }
            .report-callout, .report-body-text { font-size: 12px; color: #444; line-height: 1.55; margin: 10px 0; padding: 10px 12px; background: #fafafa; border-left: 3px solid #ddd; }
            .report-list { font-size: 12px; color: #444; line-height: 1.6; padding-left: 20px; }
            .report-footer { font-size: 11px; color: #666; margin-top: 28px; padding-top: 12px; border-top: 1px solid #ddd; }
            .report-actions { display: none; }
          </style>
        </head>
        <body>${node.innerHTML}</body>
      </html>
    `);
    w.document.close();
    w.focus();
    w.print();
  };

  if (!open) {
    return (
      <button className="explore-bubble" onClick={() => setOpen(true)}>
        Explore an area
      </button>
    );
  }

  return (
    <div className="explore-panel">
      <div className="explore-panel-header">
        <span>Explore an area</span>
        <button className="explore-close" onClick={() => setOpen(false)}>×</button>
      </div>

      <div className="explore-body">
        <div className="explore-hint">
          Click a cell on the map, or search by cell ID.
        </div>

        <div className="explore-search">
          <input
            type="text"
            placeholder="Paste a cell ID from the map"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <button onClick={handleSearch}>Go</button>
        </div>
        {error && <div className="explore-error">{error}</div>}

        <div className="explore-radius">
          <label>Radius: <strong>{radius} km</strong></label>
          <input
            type="range"
            min="2"
            max="40"
            step="1"
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
          />
        </div>

        {summary ? (
          <ExploreReport
            summary={summary}
            meta={meta}
            stats={stats}
            onPrint={handlePrint}
            countryName={countryName || country}
          />
        ) : (
          <div className="explore-empty">No cell selected. Click the map to begin.</div>
        )}
      </div>
    </div>
  );
}