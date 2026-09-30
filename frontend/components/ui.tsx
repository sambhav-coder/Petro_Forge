"use client";

import type { ReactNode } from "react";

/* =========================================================================
 * Provenance / severity badges
 * =======================================================================*/

function badgeClass(level: string): string {
  switch (level) {
    case "LOW":
    case "NOMINAL":
    case "NORMAL":
    case "HEALTHY":
    case "CALIBRATED":
      return "bg-natural/12 text-natural border-natural/30";
    case "MODERATE":
    case "ELEVATED":
    case "DEGRADED":
    case "WARNING":
      return "bg-amber-warm/15 text-amber-warm border-amber-warm/35";
    case "HIGH":
    case "CRITICAL":
      return "bg-rose-500/15 text-rose-300 border-rose-500/35";
    default:
      return "bg-petroleum/25 text-natural/90 border-natural/20";
  }
}

export function Pill({ level }: { level: string }) {
  return (
    <span
      className={`badge ${badgeClass(level)}`}
      aria-label={`Status: ${level}`}
    >
      {level}
    </span>
  );
}

export function ProvenanceBadge({ kind }: { kind: string }) {
  const short = kind.replace(/_BAGHEWALA$/, "");
  let cls = "bg-forest-deep text-sand/80 border-sand/20";
  if (kind === "BAGHEWALA_FIELD" || short === "FIELD")
    cls = "bg-natural/10 text-natural border-natural/25";
  else if (kind === "SYNTHETIC_BAGHEWALA" || short === "SYNTHETIC")
    cls = "bg-amber-warm/12 text-amber-warm border-amber-warm/30";
  else if (short === "DERIVED")
    cls = "bg-amber-warm/10 text-amber-warm/90 border-amber-warm/25";
  else if (short === "LIVE_TELEMETRY" || short === "LIVE")
    cls = "bg-natural/12 text-natural border-natural/30";
  else if (short === "PUBLIC_REFERENCE")
    cls = "bg-sky-500/10 text-sky-300 border-sky-500/25";
  else if (short === "INSUFFICIENT")
    cls = "bg-slate-700/50 text-slate-300 border-slate-600/40";
  return <span className={`badge ${cls}`}>{short}</span>;
}

/* =========================================================================
 * Key / value rows
 * =======================================================================*/

export function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div className="text-xs font-mono space-y-1.5">
      {rows.map(([k, v]) => (
        <div
          key={k}
          className="flex justify-between gap-3 items-start py-0.5 border-b border-natural/5 last:border-0"
        >
          <span className="text-sand/55 whitespace-nowrap">{k}</span>
          <span className="text-cream-soft/95 text-right break-words">
            {v}
          </span>
        </div>
      ))}
    </div>
  );
}

/* =========================================================================
 * Section header
 * =======================================================================*/

export function Section({
  title,
  children,
  right,
}: {
  title: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2 pb-1">
        <h4 className="text-[10.5px] font-semibold font-mono text-sand/85 tracking-[0.18em] uppercase">
          {title}
        </h4>
        {right}
      </div>
      {children}
    </section>
  );
}

/* =========================================================================
 * KPI tile
 * =======================================================================*/

export function Kpi({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "good" | "bad" | "warn";
}) {
  const color =
    tone === "good"
      ? "text-natural"
      : tone === "bad"
        ? "text-rose-300"
        : tone === "warn"
          ? "text-amber-warm"
          : "text-cream-soft";
  return (
    <div
      className="rounded-lg bg-oil-black/45 border border-natural/10 px-2.5 py-2 shadow-inner-glow"
      style={{ backdropFilter: "blur(4px)" }}
    >
      <div className="text-[9px] font-mono text-sand/45 uppercase tracking-[0.14em]">
        {label}
      </div>
      <div className={`text-[13.5px] font-mono font-semibold mt-0.5 ${color}`}>
        {value}
        {unit && (
          <span className="text-[10px] font-normal text-sand/45 ml-1">
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

/* =========================================================================
 * Notes / loading / error / button / delta
 * =======================================================================*/

export function Note({ children }: { children: ReactNode }) {
  return (
    <p className="text-[10.5px] leading-relaxed text-sand/50 font-sans">
      {children}
    </p>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="text-xs font-mono text-sand/45 flex items-center gap-2">
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-natural/60 animate-pulseSoft" />
      Loading {what}…
    </p>
  );
}

export function ErrorLine({ error }: { error: string }) {
  return (
    <p className="text-xs font-mono text-rose-300/90 bg-rose-500/8 border border-rose-500/25 rounded-md px-2.5 py-1.5">
      {error}
    </p>
  );
}

export function PrimaryButton({
  onClick,
  disabled,
  children,
  className = "",
}: {
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`cta-primary inline-flex items-center gap-2 px-4 py-2 rounded-lg text-[11px] font-semibold font-mono tracking-[0.1em] uppercase text-cream-soft
        bg-gradient-to-r from-forest-deep via-petroleum to-crude/80
        border border-natural/35
        shadow-glow
        disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:transform-none
        ${className}`}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  onClick,
  disabled,
  children,
  className = "",
}: {
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`pill-btn inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-[11px] font-mono font-semibold tracking-[0.08em] uppercase text-sand/90
        bg-oil-black/40 border border-natural/15 hover:border-natural/35 hover:text-cream-soft
        disabled:opacity-40 disabled:cursor-not-allowed
        ${className}`}
    >
      {children}
    </button>
  );
}

export function Delta({
  v,
  digits = 1,
  goodWhen = "up",
  unit = "",
}: {
  v: number | null | undefined;
  digits?: number;
  goodWhen?: "up" | "down";
  unit?: string;
}) {
  if (v === null || v === undefined || Number.isNaN(v))
    return <span className="text-sand/40">—</span>;
  const good = goodWhen === "up" ? v > 0 : v < 0;
  const flat = Math.abs(v) < 10 ** -digits / 2;
  const color = flat
    ? "text-sand/55"
    : good
      ? "text-natural"
      : "text-rose-300";
  return (
    <span className={`font-mono font-semibold ${color}`}>
      {v > 0 ? "+" : ""}
      {v.toFixed(digits)}
      {unit}
    </span>
  );
}

/* =========================================================================
 * Control panel header bar (for twin page)
 * =======================================================================*/

export function PanelHeader({
  title,
  kicker,
  onClose,
  right,
}: {
  title: string;
  kicker?: string;
  onClose?: () => void;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-natural/10">
      <div className="min-w-0">
        {kicker && (
          <div className="text-[9.5px] font-mono text-natural/70 tracking-[0.22em] uppercase">
            {kicker}
          </div>
        )}
        <div className="text-[12.5px] font-semibold font-display tracking-[0.06em] text-cream-soft truncate">
          {title}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {right}
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Collapse panel"
            className="pill-btn w-7 h-7 flex items-center justify-center rounded-md border border-natural/15 text-sand/55 hover:text-cream-soft hover:border-natural/35 text-sm"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

/* =========================================================================
 * Segmented tab strip
 * =======================================================================*/

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (t: T) => void;
}) {
  return (
    <div
      className="flex gap-0.5 p-0.5 rounded-lg bg-oil-black/50 border border-natural/10 overflow-x-auto scroll-thin"
      role="tablist"
    >
      {tabs.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={`tab-btn shrink-0 px-2.5 py-1.5 text-[10.5px] font-mono font-semibold tracking-[0.1em] uppercase rounded-md transition-all duration-200
              ${
                active
                  ? "bg-gradient-to-r from-petroleum/80 to-forest-deep text-cream-soft shadow-glow border border-natural/25"
                  : "text-sand/55 hover:text-cream-soft hover:bg-natural/5 border border-transparent"
              }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

/* =========================================================================
 * Glass panel wrapper
 * =======================================================================*/

export function GlassPanel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`glass rounded-xl overflow-hidden ${className}`}
    >
      {children}
    </div>
  );
}
