import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import { logNormalizer } from "../utils/colors";

const STOPS = [
  [0.00, [8, 6, 20]],
  [0.15, [40, 15, 75]],
  [0.35, [100, 25, 125]],
  [0.55, [175, 45, 110]],
  [0.72, [235, 85, 55]],
  [0.85, [255, 145, 30]],
  [0.95, [255, 210, 60]],
  [1.00, [255, 250, 210]],
];

function sample(t) {
  const x = Math.min(1, Math.max(0, t)) * (STOPS.length - 1);
  const i = Math.min(STOPS.length - 2, Math.floor(x));
  const f = x - i;
  const a = STOPS[i][1];
  const b = STOPS[i + 1][1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

const PAD = 200;
const BLUR = 4; // css px, same as before
const CAN_FILTER =
  typeof CanvasRenderingContext2D !== "undefined" &&
  "filter" in CanvasRenderingContext2D.prototype;

function tracePath(ctx, map, geom) {
  const rings = geom.type === "Polygon" ? geom.coordinates : geom.coordinates.flat();
  ctx.beginPath();
  for (const ring of rings) {
    for (let i = 0; i < ring.length; i++) {
      const p = map.latLngToContainerPoint([ring[i][1], ring[i][0]]);
      if (i === 0) ctx.moveTo(p.x + PAD, p.y + PAD);
      else ctx.lineTo(p.x + PAD, p.y + PAD);
    }
    ctx.closePath();
  }
}

export default function NightLightsGlow({ data, opacity = 1 }) {
  const map = useMap();
  const canvasRef = useRef(null);
  const frameRef = useRef(null);

  useEffect(() => {
    if (!data?.features?.length) return;
    const meta = data.metadata;
    const norm = logNormalizer(meta.min, meta.max);

    const canvas = L.DomUtil.create("canvas", "leaflet-glow-layer");
    canvas.style.position = "absolute";
    canvas.style.pointerEvents = "none";
    canvas.style.mixBlendMode = "multiply";
    canvas.style.zIndex = 350;
    // Safari fallback: original behavior (CSS blur on the whole canvas)
    if (!CAN_FILTER) canvas.style.filter = `blur(${BLUR}px) saturate(1.3)`;
    map.getPanes().overlayPane.appendChild(canvas);
    canvasRef.current = canvas;

    // offscreen layers: colored cells, and the sharp footprint of drawn cells
    const glow = document.createElement("canvas");
    const mask = document.createElement("canvas");

    const render = () => {
      const size = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      const padSize = { x: size.x + PAD * 2, y: size.y + PAD * 2 };
      const topLeft = map.containerPointToLayerPoint([-PAD, -PAD]);

      for (const c of [canvas, glow, mask]) {
        c.width = padSize.x * dpr;
        c.height = padSize.y * dpr;
      }
      canvas.style.width = padSize.x + "px";
      canvas.style.height = padSize.y + "px";
      L.DomUtil.setPosition(canvas, topLeft);

      const g = glow.getContext("2d");
      const m = mask.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      m.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.globalCompositeOperation = "lighter";
      m.fillStyle = "#000";

      for (const f of data.features) {
        const v = f.properties.value;
        if (v == null) continue;
        const t = norm(v);
        if (t == null) continue;

        // unchanged from your original
        const boosted = Math.pow(t, 0.75);
        const alpha = Math.min(1, boosted * 1.6) * opacity;
        if (alpha < 0.02) continue;

        const [r, gr, b] = sample(t);
        g.fillStyle = `rgba(${r},${gr},${b},${alpha})`;
        tracePath(g, map, f.geometry);
        g.fill();

        // footprint = exactly the cells that were drawn above
        tracePath(m, map, f.geometry);
        m.fill();
      }

      const ctx = canvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (CAN_FILTER) {
        // blur the glow, then clip it to the sharp footprint
        ctx.filter = `blur(${BLUR * dpr}px) saturate(1.3)`;
        ctx.drawImage(glow, 0, 0);
        ctx.filter = "none";
        ctx.globalCompositeOperation = "destination-in";
        ctx.drawImage(mask, 0, 0);
        ctx.globalCompositeOperation = "source-over";
      } else {
        ctx.drawImage(glow, 0, 0); // CSS blur handles it, no clip
      }
    };

    const schedule = () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      frameRef.current = requestAnimationFrame(render);
    };

    schedule();
    map.on("move zoom resize viewreset zoomend moveend", schedule);

    return () => {
      map.off("move zoom resize viewreset zoomend moveend", schedule);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      canvas.remove();
    };
  }, [map, data, opacity]);

  return null;
}