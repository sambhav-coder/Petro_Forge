import { LAYOUT } from "./scene";

/*
 * Prototype-relative depth system.
 * The backend provides NO depth data, so all depth is expressed as a
 * percentage of the visualization shaft (0 = surface, 100 = shaft floor).
 * If real depths ever arrive in telemetry, replace depthPctOfY / yOfPct
 * with a calibrated mapping — call sites stay unchanged.
 */

export const DEPTH_NOTE = "Prototype-relative depth — no field depth data in backend.";

export function depthPctOfY(y: number): number {
  return Math.max(0, Math.min(100, ((LAYOUT.surfaceY - y) / LAYOUT.shaftDepth) * 100));
}

export function yOfDepthPct(pct: number): number {
  const c = Math.max(0, Math.min(100, pct));
  return LAYOUT.surfaceY - (c / 100) * LAYOUT.shaftDepth;
}

/** Engineering ruler stops: surface → quarters → pump → floor. */
export function rulerStops(): { pct: number; label: string; accent?: boolean }[] {
  return [
    { pct: 0, label: "SURFACE" },
    { pct: 25, label: "25%" },
    { pct: 50, label: "50%" },
    { pct: depthPctOfY(LAYOUT.pumpY), label: "PUMP LEVEL", accent: true },
    { pct: 75, label: "75%" },
    { pct: 100, label: "SHAFT FLOOR" },
  ];
}
