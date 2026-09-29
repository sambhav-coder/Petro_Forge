"use client";

import { useEffect } from "react";
import * as THREE from "three";
import type { IsolatableKind } from "./types";

/*
 * Engineering isolation: dims every mesh whose component kind differs
 * from the isolated one. Objects are never destroyed — visibility and
 * opacity state only. Meshes tagged userData.noDim (selection shells)
 * are skipped.
 *
 * Idempotent across view-mode changes: each run first restores any
 * previously saved state, then re-applies dimming from the materials'
 * current (view-mode-correct) values.
 */

interface Saved {
  opacity: number;
  transparent: boolean;
  depthWrite: boolean;
}

/** Dim only meshes belonging to other component kinds. */
export function useKindIsolation(
  root: React.RefObject<THREE.Group | null>,
  isolated: IsolatableKind | null,
  viewModeKey: string
): void {
  useEffect(() => {
    const g = root.current;
    if (!g) return;
    const apply = (dimOthers: boolean) => {
      g.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (!mesh.isMesh && !(obj as THREE.Points).isPoints) return;
        const ud = obj.userData as Record<string, unknown>;
        if (ud.noDim) return;
        let k: THREE.Object3D | null = obj;
        let kind: string | null = null;
        while (k) {
          const v = (k.userData as Record<string, unknown>).componentKind;
          if (typeof v === "string") {
            kind = v;
            break;
          }
          k = k.parent;
        }
        const mat = mesh.material as THREE.Material | THREE.Material[];
        for (const m of Array.isArray(mat) ? mat : [mat]) {
          const std = m as THREE.MeshStandardMaterial;
          if (typeof std.opacity !== "number") continue;
          if (!dimOthers) {
            if (ud._isoSaved) {
              const saved = ud._isoSaved as Saved;
              std.opacity = saved.opacity;
              std.transparent = saved.transparent;
              std.depthWrite = saved.depthWrite;
              delete ud._isoSaved;
            }
          } else if (kind !== null && kind !== isolated) {
            if (!ud._isoSaved) {
              ud._isoSaved = {
                opacity: std.opacity,
                transparent: std.transparent,
                depthWrite: std.depthWrite,
              } as Saved;
            }
            std.transparent = true;
            std.opacity = Math.min((ud._isoSaved as Saved).opacity, 1) * 0.07;
            std.depthWrite = false;
          }
        }
      });
    };
    // Restore pass first (view-mode safe), then dim pass.
    apply(false);
    if (isolated !== null) apply(true);
  }, [root, isolated, viewModeKey]);
}
