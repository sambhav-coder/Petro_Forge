"use client";

/*
 * PressureOverlay — FUTURE pressure-visualization layer (Phase 2+).
 *
 * Interface contract (reserved):
 *   <PressureOverlay wellId twin={...} visible={...} />
 * would render a spatial pressure field derived from REAL spatial
 * pressure data. No such data exists in the backend (only scalar
 * reservoir/wellhead pressures), so this layer stays DISABLED and
 * renders nothing. Pressure values remain visible in the inspector
 * as backend scalars. Do NOT invent a pressure field here.
 */

import type { TwinSnapshot } from "@/lib/types";

export const PRESSURE_OVERLAY_ENABLED = false;

export default function PressureOverlay({
  wellId,
  twin,
  visible,
}: {
  wellId: string;
  twin: TwinSnapshot | null;
  visible: boolean;
}) {
  void wellId;
  void twin;
  void visible;
  if (!PRESSURE_OVERLAY_ENABLED) return null;
  return null;
}
