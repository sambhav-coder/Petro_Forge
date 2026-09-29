import type { ObjectKind } from "./types";

/*
 * Shared visual language + prototype-geometry notes.
 * Geometry here is STYLIZED prototype visualization (relative units).
 * No real well dimensions, depths, or equipment specs are claimed.
 * Engineering metadata always comes from the backend twin/telemetry.
 */

export const COLORS = {
  bg: "#070b14",
  sandstone: "#8a6844",
  sandstoneDeep: "#4a3826",
  oilAmber: "#f5a524",
  oilDeep: "#b45309",
  heatHot: "#ff6b35",
  steel: "#9aa7b8",
  steelDark: "#3a4354",
  rodMetal: "#1f2733",
  casing: "#5b6b82",
  selectTeal: "#2dd4bf",
  warn: "#fbbf24",
  critical: "#fb7185",
  healthy: "#34d399",
  grid: "#1e2a44",
} as const;

/* Relative scene layout (prototype units, NOT field dimensions). */
export const LAYOUT = {
  surfaceY: 0,
  shaftHalfWidth: 3.2,
  shaftDepth: 26,
  reservoirTop: -17,
  reservoirBottom: -24,
  pumpY: -21,
  wellSpacing: 16,
} as const;

export const OBJECT_META: Record<ObjectKind, { title: string; hint: string }> = {
  well: { title: "Well", hint: "Engineered asset — telemetry + twin state" },
  wellhead: { title: "Wellhead", hint: "Surface pressure boundary + production outlet" },
  srp: { title: "SRP Surface Unit", hint: "Beam pumping unit — motion follows SPM" },
  tubing: { title: "Production Tubing", hint: "Production fluid path to surface" },
  rod: { title: "Rod String", hint: "Reciprocating drive string — see rod-float indicator" },
  pump: { title: "Downhole Pump", hint: "Positive-displacement lift point" },
  reservoir: { title: "Reservoir", hint: "Jodhpur Sandstone (prototype volume) — thermal state" },
};

/** Map scalar twin temperature onto a 0..1 thermal-visual intensity. */
export function thermalVisual(
  estimatedC: number,
  baselineC: number
): number {
  const span = Math.max(estimatedC - baselineC, 0);
  // Visual mapping only — not a spatial temperature field.
  return Math.min(1, 0.15 + span / 120);
}

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}
