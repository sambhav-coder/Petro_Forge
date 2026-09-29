"use client";

/* Dependency-free SVG charts sized for the 400px inspector.
   Every value plotted comes from a backend response. */

export interface Series {
  name: string;
  color: string;
  points: [number, number][];
  dashed?: boolean;
  width?: number;
  /* Continuation segment of an earlier series (same colour, no legend entry). */
  hideLegend?: boolean;
}

export interface Band {
  x0: number;
  x1: number;
  color: string;
  label?: string;
}

export interface Marker {
  x: number;
  label: string;
  color: string;
}

const W = 360;
const PAD = { l: 38, r: 8, t: 10, b: 22 };

function niceTicks(lo: number, hi: number, n = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function short(v: number): string {
  const a = Math.abs(v);
  if (a >= 10000) return `${(v / 1000).toFixed(0)}k`;
  if (a >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(0);
  return v.toFixed(a >= 1 ? 1 : 2);
}

export function LineChart({
  series,
  height = 150,
  bands = [],
  markers = [],
  xLabel,
  yLabel,
  yMin,
  xFormat = short,
}: {
  series: Series[];
  height?: number;
  bands?: Band[];
  markers?: Marker[];
  xLabel?: string;
  yLabel?: string;
  yMin?: number;
  xFormat?: (v: number) => string;
}) {
  const all = series.flatMap((s) => s.points);
  if (all.length < 2) {
    return <div className="text-[11px] font-mono text-slate-500 py-6 text-center">Not enough data to plot.</div>;
  }
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const yLo = yMin ?? Math.min(0, ...ys);
  const yHiRaw = Math.max(...ys);
  const yHi = yHiRaw > yLo ? yHiRaw * 1.08 : yLo + 1;
  const iw = W - PAD.l - PAD.r;
  const ih = height - PAD.t - PAD.b;
  const sx = (x: number) => PAD.l + (x1 > x0 ? ((x - x0) / (x1 - x0)) * iw : iw / 2);
  const sy = (y: number) => PAD.t + ih - ((y - yLo) / (yHi - yLo)) * ih;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full h-auto" role="img">
        {bands.map((b, i) => (
          <g key={`b${i}`}>
            <rect x={sx(b.x0)} y={PAD.t} width={Math.max(sx(b.x1) - sx(b.x0), 0)} height={ih} fill={b.color} />
            {b.label && sx(b.x1) - sx(b.x0) > 26 && (
              <text x={(sx(b.x0) + sx(b.x1)) / 2} y={PAD.t + 9} fontSize="8" textAnchor="middle" fill="#94a3b8">
                {b.label}
              </text>
            )}
          </g>
        ))}
        {niceTicks(yLo, yHi).map((t) => (
          <g key={`y${t}`}>
            <line x1={PAD.l} x2={W - PAD.r} y1={sy(t)} y2={sy(t)} stroke="#1e293b" strokeWidth="1" />
            <text x={PAD.l - 4} y={sy(t) + 3} fontSize="8" textAnchor="end" fill="#64748b">{short(t)}</text>
          </g>
        ))}
        {niceTicks(x0, x1, 5).map((t) => (
          <text key={`x${t}`} x={sx(t)} y={height - 8} fontSize="8" textAnchor="middle" fill="#64748b">
            {xFormat(t)}
          </text>
        ))}
        {markers.map((m, i) => (
          <g key={`m${i}`}>
            <line x1={sx(m.x)} x2={sx(m.x)} y1={PAD.t} y2={PAD.t + ih} stroke={m.color} strokeWidth="1.2" strokeDasharray="3 2" />
            <text x={Math.min(sx(m.x) + 3, W - 60)} y={PAD.t + 18 + i * 10} fontSize="8" fill={m.color}>{m.label}</text>
          </g>
        ))}
        {series.map((s, i) => (
          <polyline
            key={`${s.name}-${i}`}
            fill="none"
            stroke={s.color}
            strokeWidth={s.width ?? 1.6}
            strokeDasharray={s.dashed ? "4 3" : undefined}
            strokeLinejoin="round"
            points={s.points.map(([x, y]) => `${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join(" ")}
          />
        ))}
        {yLabel && (
          <text x={4} y={PAD.t + 2} fontSize="8" fill="#64748b">{yLabel}</text>
        )}
        {xLabel && (
          <text x={W - PAD.r} y={height - 1} fontSize="8" textAnchor="end" fill="#64748b">{xLabel}</text>
        )}
      </svg>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
        {series.filter((s) => !s.hideLegend).map((s) => (
          <span key={s.name} className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
            <span className="inline-block w-3 h-0.5" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DynaCardChart({
  points,
  refLines = [],
  height = 190,
}: {
  points: { position_in: number; load_lb: number }[];
  refLines?: { y: number; label: string; color: string }[];
  height?: number;
}) {
  if (points.length < 3) return null;
  const xs = points.map((p) => p.position_in);
  const ys = [...points.map((p) => p.load_lb), ...refLines.map((r) => r.y), 0];
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const yLo = Math.min(...ys);
  const yHi = Math.max(...ys) * 1.06;
  const iw = W - PAD.l - PAD.r;
  const ih = height - PAD.t - PAD.b;
  const sx = (x: number) => PAD.l + ((x - x0) / Math.max(x1 - x0, 1e-6)) * iw;
  const sy = (y: number) => PAD.t + ih - ((y - yLo) / Math.max(yHi - yLo, 1e-6)) * ih;
  const path = points.map((p) => `${sx(p.position_in).toFixed(1)},${sy(p.load_lb).toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full h-auto" role="img">
      {niceTicks(yLo, yHi).map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(t)} y2={sy(t)} stroke="#1e293b" />
          <text x={PAD.l - 4} y={sy(t) + 3} fontSize="8" textAnchor="end" fill="#64748b">{short(t)}</text>
        </g>
      ))}
      {niceTicks(x0, x1, 4).map((t) => (
        <text key={`x${t}`} x={sx(t)} y={height - 8} fontSize="8" textAnchor="middle" fill="#64748b">{short(t)}</text>
      ))}
      {yLo < 0 && <line x1={PAD.l} x2={W - PAD.r} y1={sy(0)} y2={sy(0)} stroke="#fb7185" strokeWidth="1" />}
      {refLines.map((r) => (
        <g key={r.label}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(r.y)} y2={sy(r.y)} stroke={r.color} strokeDasharray="4 3" strokeWidth="1" />
          <text x={W - PAD.r - 2} y={sy(r.y) - 3} fontSize="8" textAnchor="end" fill={r.color}>{r.label}</text>
        </g>
      ))}
      <polygon points={path} fill="rgba(45,212,191,0.10)" stroke="#2dd4bf" strokeWidth="1.8" strokeLinejoin="round" />
      <text x={4} y={PAD.t + 2} fontSize="8" fill="#64748b">load lb</text>
      <text x={W - PAD.r} y={height - 1} fontSize="8" textAnchor="end" fill="#64748b">rod position, in</text>
    </svg>
  );
}

export function ProbabilityBar({ p, band }: { p: number; band: string }) {
  const color = band === "HIGH" ? "#fb7185" : band === "MODERATE" ? "#fbbf24" : "#34d399";
  return (
    <div className="h-2 w-full rounded bg-slate-800 overflow-hidden">
      <div className="h-full rounded" style={{ width: `${Math.max(p * 100, 1.5)}%`, background: color }} />
    </div>
  );
}
