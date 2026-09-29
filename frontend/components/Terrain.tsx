"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { COLORS, LAYOUT } from "@/lib/scene";
import { rulerStops, yOfDepthPct } from "@/lib/depth";
import type { ViewMode } from "@/lib/types";

/* Deterministic pseudo-noise — no Math.random anywhere. */
function groundH(x: number, z: number): number {
  return (
    0.35 * Math.sin(x * 0.32) * Math.cos(z * 0.27) +
    0.16 * Math.sin(x * 0.83 + z * 0.61) +
    0.08 * Math.cos(x * 1.7 - z * 1.3)
  );
}

function DisplacedPlane({
  cx,
  cz,
  w,
  d,
}: {
  cx: number;
  cz: number;
  w: number;
  d: number;
}) {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(Math.max(w, 0.01), Math.max(d, 0.01), 36, 20);
    const pos = g.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) + cx;
      const z = pos.getY(i) + cz; // plane local Y maps to world -Z after rotation
      pos.setZ(i, groundH(x, z));
    }
    g.computeVertexNormals();
    return g;
  }, [cx, cz, w, d]);
  if (w <= 0.02 || d <= 0.02) return null;
  return (
    <mesh geometry={geo} rotation={[-Math.PI / 2, 0, 0]} position={[cx, 0, cz]} receiveShadow>
      <meshStandardMaterial color="#2c2417" roughness={1} metalness={0.02} />
    </mesh>
  );
}

const STRATA = ["#6b543a", "#4a3826", "#33271a", "#54402c", "#2b2115"];

function StrataWall({
  position,
  rotationY,
  width,
  opacity,
}: {
  position: [number, number, number];
  rotationY: number;
  width: number;
  opacity: number;
}) {
  const layers = useMemo(() => {
    const out: { y: number; h: number; c: string }[] = [];
    let y = 0.4;
    let i = 0;
    while (y > LAYOUT.shaftDepth * -1 - 1) {
      const h = 2.1 + (i % 3) * 0.5;
      out.push({ y: y - h / 2, h, c: STRATA[i % STRATA.length] });
      y -= h;
      i++;
    }
    return out;
  }, []);
  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      {layers.map((l, i) => (
        <mesh key={i} position={[0, l.y, 0]} receiveShadow>
          <boxGeometry args={[width, l.h, 0.5]} />
          <meshStandardMaterial color={l.c} roughness={0.95} metalness={0.03}
            transparent opacity={opacity} />
        </mesh>
      ))}
    </group>
  );
}

/* Engineering depth ruler: prototype-relative percentages (0 = surface,
   100 = shaft floor) plus pump-level marker. No field depths are claimed. */
function DepthRuler({ x }: { x: number }) {
  const stops = rulerStops();
  return (
    <group>
      <mesh position={[x, -13, 2.9]}>
        <boxGeometry args={[0.08, 26, 0.08]} />
        <meshStandardMaterial color={COLORS.selectTeal} emissive={COLORS.selectTeal} emissiveIntensity={0.5} />
      </mesh>
      {stops.map((s) => {
        const y = yOfDepthPct(s.pct);
        return (
        <group key={s.label}>
          <mesh position={[x, y, 2.9]}>
            <boxGeometry args={[s.accent ? 1.1 : 0.7, 0.07, 0.07]} />
            <meshStandardMaterial
              color={s.accent ? COLORS.oilAmber : COLORS.selectTeal}
              emissive={s.accent ? COLORS.oilAmber : COLORS.selectTeal}
              emissiveIntensity={0.6} />
          </mesh>
          <Html position={[x + 0.4, y, 2.9]} center>
            <div
              style={{
                fontSize: 10,
                fontFamily: "monospace",
                color: "#99f6e4",
                whiteSpace: "nowrap",
                textShadow: "0 0 6px #000",
              }}
            >
              {s.label}
            </div>
          </Html>
          {s.accent && (
            <Html position={[x + 0.4, y - 0.9, 2.9]} center>
              <div style={{ fontSize: 9, fontFamily: "monospace", color: "#78716c", whiteSpace: "nowrap" }}>
                *prototype-relative
              </div>
            </Html>
          )}
        </group>
        );
      })}
    </group>
  );
}

export default function Terrain({
  sites,
  selectedWellIndex,
  viewMode,
}: {
  sites: number[];
  selectedWellIndex: number;
  viewMode: ViewMode;
}) {
  const hw = LAYOUT.shaftHalfWidth;
  const sorted = useMemo(() => [...sites].sort((a, b) => a - b), [sites]);
  const minX = sorted[0] - 14;
  const maxX = sorted[sorted.length - 1] + 14;
  const midX = (minX + maxX) / 2;
  const fullW = maxX - minX;

  // Formation readability per view mode.
  const strataOpacity = viewMode === "NORMAL" ? 1 : viewMode === "CUTAWAY" ? 0.32 : 0.09;
  const strips = useMemo(() => {
    const edges = [minX, ...sorted.flatMap((s) => [s - hw, s + hw]), maxX];
    const out: { cx: number; w: number }[] = [];
    for (let i = 0; i < edges.length; i += 2) {
      const w = edges[i + 1] - edges[i];
      if (w > 0.05) out.push({ cx: (edges[i] + edges[i + 1]) / 2, w });
    }
    return out;
  }, [sorted, minX, maxX, hw]);

  return (
    <group>
      {/* Back region (z -23..-3) and front region (z 3..10) */}
      <DisplacedPlane cx={midX} cz={-13} w={fullW} d={20} />
      <DisplacedPlane cx={midX} cz={6.5} w={fullW} d={7} />
      {/* Shaft strip segments with openings */}
      {strips.map((s, i) => (
        <DisplacedPlane key={i} cx={s.cx} cz={0} w={s.w} d={6} />
      ))}
      {/* Shaft walls + floor per site */}
      {sites.map((sx, i) => (
        <group key={sx} position={[sx, 0, 0]}>
          <StrataWall position={[-hw, 0, 0]} rotationY={Math.PI / 2} width={6} opacity={strataOpacity} />
          <StrataWall position={[hw, 0, 0]} rotationY={Math.PI / 2} width={6} opacity={strataOpacity} />
          <StrataWall position={[0, 0, -3]} rotationY={0} width={hw * 2} opacity={strataOpacity} />
          <mesh position={[0, LAYOUT.shaftDepth * -1 - 0.4, 0]} receiveShadow>
            <boxGeometry args={[hw * 2, 0.8, 6]} />
            <meshStandardMaterial color="#171208" roughness={1} />
          </mesh>
          {i === selectedWellIndex && <DepthRuler x={-hw + 0.35} />}
        </group>
      ))}
      {/* Perimeter survey frame */}
      {(
        [
          [midX, 0.15, 10.2, fullW + 3],
          [midX, 0.15, -23.2, fullW + 3],
        ] as [number, number, number, number][]
      ).map((p, i) => (
        <mesh key={i} position={[p[0], p[1], p[2]]}>
          <boxGeometry args={[p[3], 0.08, 0.08]} />
          <meshStandardMaterial
            color={COLORS.selectTeal}
            emissive={COLORS.selectTeal}
            emissiveIntensity={0.35}
          />
        </mesh>
      ))}
    </group>
  );
}
