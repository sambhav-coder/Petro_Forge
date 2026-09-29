"use client";

import type { ReactNode } from "react";

export function Pill({ level }: { level: string }) {
  const cls =
    level === "LOW" || level === "NOMINAL" || level === "NORMAL"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : level === "MODERATE" || level === "ELEVATED"
        ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
        : "bg-rose-500/15 text-rose-300 border-rose-500/30";
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border font-mono ${cls}`}>
      {level}
    </span>
  );
}

export function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div className="text-xs font-mono space-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2">
          <span className="text-slate-400">{k}</span>
          <span className="text-slate-100 text-right">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-bold text-slate-300 tracking-wide">{title}</h4>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Kpi({ label, value, unit, tone }: { label: string; value: string; unit?: string; tone?: "good" | "bad" | "warn" }) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : tone === "warn" ? "text-amber-300" : "text-slate-100";
  return (
    <div className="rounded-lg bg-slate-800/50 border border-slate-700/50 px-2 py-1.5">
      <div className="text-[9px] font-mono text-slate-500 uppercase tracking-wide">{label}</div>
      <div className={`text-sm font-mono font-bold ${color}`}>
        {value}
        {unit && <span className="text-[10px] text-slate-500 font-normal ml-0.5">{unit}</span>}
      </div>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-[10px] leading-snug text-slate-500">{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return <p className="text-xs text-slate-500 font-mono">Loading {what}…</p>;
}

export function ErrorLine({ error }: { error: string }) {
  return <p className="text-xs text-rose-300 font-mono">{error}</p>;
}

export function PrimaryButton({ onClick, disabled, children }: { onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-2 rounded-lg bg-gradient-to-r from-forest-700 to-leaf text-white text-xs font-bold disabled:opacity-40"
    >
      {children}
    </button>
  );
}

/* Signed delta with a "good direction" so colour follows engineering meaning. */
export function Delta({ v, digits = 1, goodWhen = "up", unit = "" }: { v: number | null | undefined; digits?: number; goodWhen?: "up" | "down"; unit?: string }) {
  if (v === null || v === undefined || Number.isNaN(v)) return <span className="text-slate-500">—</span>;
  const good = goodWhen === "up" ? v > 0 : v < 0;
  const flat = Math.abs(v) < 10 ** -digits / 2;
  const color = flat ? "text-slate-400" : good ? "text-emerald-300" : "text-rose-300";
  return (
    <span className={color}>
      {v > 0 ? "+" : ""}
      {v.toFixed(digits)}
      {unit}
    </span>
  );
}
