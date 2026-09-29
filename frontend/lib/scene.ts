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
  /* PetroForge surface environment: arid Rajasthan-inspired tones */
  soil: "#6b4f33",
  soilDark: "#3a2a1a",
  sand: "#c9a06a",
  gravel: "#4a4238",
  grass: "#5a7a45",
  grassDark: "#3d5a2e",
  rock: "#6e6259",
  leaf: "#4ade80",
  forest: "#1d3a2a",
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
  casing: { title: "Casing", hint: "Structural wellbore liner (prototype visualization)" },
  tubing: { title: "Production Tubing", hint: "Production fluid path to surface" },
  rod: { title: "Rod String", hint: "Reciprocating drive string — see rod-float indicator" },
  pump: { title: "Downhole Pump", hint: "Positive-displacement lift point" },
  reservoir: { title: "Oil-Bearing Zone", hint: "Heavy-oil sandstone volume — thermal state" },
  thermal: { title: "Thermal Zone", hint: "Visual mapping of the scalar twin temperature" },
  formation: { title: "Formation Rock", hint: "Cap / base rock — structural context only" },
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
