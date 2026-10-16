import { NO_DATA, PALETTES, gradientCss } from "../utils/colors";
import { fmtLayerValue } from "../utils/format";

export default function Legend({ meta, showInfra, infraMeta }) {
  if (!meta) return null;
  const stops = PALETTES[meta.layer];
  return (
    <div className="legend" aria-label={`Legend for ${meta.name}`}>
      <strong>{meta.name}</strong>
      <span className="legend-unit">{meta.unit}{meta.scale === "log" ? " · log scale" : ""}</span>
      <div className="legend-bar" style={{ background: gradientCss(stops) }} />
      <div className="legend-labels">
        <span>{meta.legend.low}</span>
        <span>{meta.legend.high}</span>
      </div>
      <div className="legend-labels legend-numbers">
        <span>{fmtLayerValue(meta.min, meta.unit)}</span>
        <span>{fmtLayerValue(meta.max, meta.unit)}</span>
      </div>
      {meta.n_missing > 0 && (
        <div className="legend-row"><span className="swatch" style={{ background: NO_DATA }} /> No data ({meta.n_missing} {meta.admin_level ? "areas" : "cells"})</div>
      )}
      <div className="legend-row"><span className="swatch swatch-selected" /> Selected</div>
      {showInfra && (
        <div className="legend-infra">
          <div className="legend-row"><span className="line line-hv" /> Power line (OSM)</div>
          <div className="legend-row"><span className="line line-minor" /> Minor line / cable</div>
          <div className="legend-row"><span className="dot dot-sub" /> Substation</div>
          <div className="legend-row"><span className="dot dot-plant" /> Power plant</div>
          {!infraMeta?.counts?.minigrid && <small>No verified minigrid dataset is available.</small>}
        </div>
      )}
      <small className="legend-source">
        {meta.kind} · {meta.source}{meta.source_date ? ` · ${meta.source_date}` : ""}
      </small>
    </div>
  );
}
