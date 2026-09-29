import type { IsolatableKind, ObjectKind } from "./types";
import { LAYOUT } from "./scene";

/*
 * Component registry — single source of truth for scene entities.
 * Future phases (pump dissection, history, ML overlays) register here
 * without rewriting the inspector or selection plumbing.
 *
 * depthPct: prototype-relative position in the visualization
 * (0 = surface, 100 = shaft floor). NOT field depth.
 */

export interface ComponentSpec {
  kind: ObjectKind;
  displayName: string;
  /** Prototype-relative depth span [topPct, bottomPct]. */
  depthPct: [number, number];
  isolatable: boolean;
  blurb: string;
}

const pct = (y: number): number =>
  Math.max(0, Math.min(100, ((LAYOUT.surfaceY - y) / LAYOUT.shaftDepth) * 100));

export const COMPONENTS: Record<ObjectKind, ComponentSpec> = {
  well: {
    kind: "well",
    displayName: "Well (aggregate)",
    depthPct: [0, 100],
    isolatable: false,
    blurb: "Whole engineered asset.",
  },
  wellhead: {
    kind: "wellhead",
    displayName: "Wellhead",
    depthPct: [0, pct(-2)],
    isolatable: true,
    blurb: "Surface pressure boundary and production outlet.",
  },
  srp: {
    kind: "srp",
    displayName: "SRP Surface Unit",
    depthPct: [0, pct(-6)],
    isolatable: false,
    blurb: "Beam pumping unit; animation follows backend SPM.",
  },
  casing: {
    kind: "casing",
    displayName: "Casing",
    depthPct: [pct(-0.6), pct(-17.6)],
    isolatable: true,
    blurb: "Structural liner of the wellbore (prototype visualization).",
  },
  tubing: {
    kind: "tubing",
    displayName: "Production Tubing",
    depthPct: [pct(-0.8), pct(-20)],
    isolatable: true,
    blurb: "Production fluid path from pump to surface.",
  },
  rod: {
    kind: "rod",
    displayName: "Rod String",
    depthPct: [pct(-4.3), pct(-19.8)],
    isolatable: true,
    blurb: "Reciprocating drive string between unit and pump.",
  },
  pump: {
    kind: "pump",
    displayName: "Downhole Pump",
    depthPct: [pct(LAYOUT.pumpY - 1.8), pct(LAYOUT.pumpY + 1.8)],
    isolatable: true,
    blurb: "Downhole positive-displacement lift point.",
  },
  reservoir: {
    kind: "reservoir",
    displayName: "Oil-Bearing Zone",
    depthPct: [pct(LAYOUT.reservoirTop), pct(LAYOUT.reservoirBottom)],
    isolatable: true,
    blurb: "Heavy-oil sandstone volume (prototype geometry).",
  },
  thermal: {
    kind: "thermal",
    displayName: "Thermal Zone",
    depthPct: [pct(LAYOUT.reservoirTop), pct(LAYOUT.reservoirBottom)],
    isolatable: true,
    blurb: "Scalar twin-temperature mapping — not a thermal solver.",
  },
  formation: {
    kind: "formation",
    displayName: "Formation Rock",
    depthPct: [0, 100],
    isolatable: true,
    blurb: "Cap / base rock — structural context, no backend metrics.",
  },
};

export function isIsolatable(kind: ObjectKind): kind is IsolatableKind {
  return COMPONENTS[kind].isolatable;
}
