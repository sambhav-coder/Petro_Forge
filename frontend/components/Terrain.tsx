"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { COLORS, LAYOUT } from "@/lib/scene";
import { rulerStops, yOfDepthPct } from "@/lib/depth";
import type { ViewMode } from "@/lib/types";

/*
 * Surface environment: stylized arid Rajasthan-inspired well site.
 * Warm soil + sand + controlled sparse vegetation + industrial pad.
 * NOT a claim about real Baghewala surface geography.
 * All placement is deterministic — no Math.random anywhere.
 */

/* Deterministic hash noise in [0, 1). */
function hash(i: number, seed: number): number {
  const s = Math.sin(i * 127.1 + seed * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function groundH(x: number, z: number): number {
  return (
    0.35 * Math.sin(x * 0.32) * Math.cos(z * 0.27) +
    0.16 * Math.sin(x * 0.83 + z * 0.61) +
    0.08 * Math.cos(x * 1.7 - z * 1.3)
  );
}

function nearPad(x: number, z: number, sites: number[], r: number): boolean {
  return sites.some((sx) => Math.hypot(x - sx, z * 0.8) < r);
}

const C = {
  soil: new THREE.Color(COLORS.soil),
  soilDark: new THREE.Color(COLORS.soilDark),
  sand: new THREE.Color(COLORS.sand),
  gravel: new THREE.Color(COLORS.gravel),
  grass: new THREE.Color(COLORS.grass),
  grassDark: new THREE.Color(COLORS.grassDark),
  tmp: new THREE.Color(),
};

/* Land-cover color: sand/soil base, patchy sparse green, disturbed earth near pads. */
function surfaceColor(x: number, z: number, sites: number[], out: THREE.Color): THREE.Color {
  const n1 = 0.5 + 0.5 * Math.sin(x * 0.45 + z * 0.3) * Math.cos(x * 0.2 - z * 0.5);
  const n2 = 0.5 + 0.5 * Math.sin(x * 1.1 + 2.0) * Math.sin(z * 0.9 + 1.0);
  out.copy(C.sand).lerp(C.soil, Math.min(1, Math.max(0, n1)));
  // Sparse vegetation patches (~25% cover, kept dull for arid feel).
  if (n2 > 0.72) out.lerp(n2 > 0.86 ? C.grass : C.grassDark, 0.75);
  // Compacted / disturbed earth around pads and shafts.
  if (nearPad(x, z, sites, 8.5)) out.lerp(C.gravel, 0.45);
  if (nearPad(x, z, sites, 6.2)) out.lerp(C.soilDark, 0.35);
  return out;
}

function DisplacedPlane({
  cx,
  cz,
  w,
  d,
  sites,
}: {
  cx: number;
  cz: number;
  w: number;
  d: number;
  sites: number[];
}) {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(Math.max(w, 0.01), Math.max(d, 0.01), 36, 20);
    const pos = g.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) + cx;
      const z = pos.getY(i) + cz; // plane local Y maps to world -Z after rotation
      pos.setZ(i, groundH(x, z));
      surfaceColor(x, z, sites, C.tmp);
      colors[i * 3] = C.tmp.r;
      colors[i * 3 + 1] = C.tmp.g;
      colors[i * 3 + 2] = C.tmp.b;
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    g.computeVertexNormals();
    return g;
  }, [cx, cz, w, d, sites]);
  if (w <= 0.02 || d <= 0.02) return null;
  return (
    <mesh geometry={geo} rotation={[-Math.PI / 2, 0, 0]} position={[cx, 0, cz]} receiveShadow>
      <meshStandardMaterial vertexColors roughness={1} metalness={0.02} />
    </mesh>
  );
}

/* Compacted well pad + disturbed-soil ring + access tracks per site. */
function WellPad({ x }: { x: number }) {
  return (
    <group position={[x, 0, 0]}>
      {/* Disturbed soil ring */}
      <mesh position={[0.8, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <ringGeometry args={[5.4, 7.4, 40]} />
        <meshStandardMaterial color={COLORS.soilDark} roughness={1} />
      </mesh>
      {/* Compacted gravel pad */}
      <mesh position={[0.8, 0.1, 0]} receiveShadow>
        <cylinderGeometry args={[5.4, 5.7, 0.22, 36]} />
        <meshStandardMaterial color={COLORS.gravel} roughness={0.95} />
      </mesh>
      {/* Access tracks leading to the pad */}
      {[-1.1, 1.1].map((dz) => (
        <mesh key={dz} position={[0.8 + dz * 0.2, 0.06, 8.5]} receiveShadow>
          <boxGeometry args={[0.9, 0.05, 9]} />
          <meshStandardMaterial color={COLORS.soilDark} roughness={1} />
        </mesh>
      ))}
    </group>
  );
}

/* Chamfered excavation collar so the cutaway reads as a dug section. */
function ExcavationRim({ hw }: { hw: number }) {
  const rim = { color: COLORS.soil, roughness: 1 };
  const top = { color: "#241a10", roughness: 1 };
  return (
    <group>
      {[
        { p: [0, 0.35, -3.35] as [number, number, number], r: [0.5, 0, 0] as [number, number, number], w: hw * 2 + 1.6 },
        { p: [0, 0.35, 3.35] as [number, number, number], r: [-0.5, 0, 0] as [number, number, number], w: hw * 2 + 1.6 },
        { p: [-hw - 0.35, 0.35, 0] as [number, number, number], r: [0, 0, 0.5] as [number, number, number], w: 7.4 },
        { p: [hw + 0.35, 0.35, 0] as [number, number, number], r: [0, 0, -0.5] as [number, number, number], w: 7.4 },
      ].map((s, i) => (
        <group key={i} position={s.p} rotation={s.r}>
          <mesh castShadow receiveShadow>
            <boxGeometry args={[s.w, 0.9, 0.7]} />
            <meshStandardMaterial {...rim} />
          </mesh>
          <mesh position={[0, 0.48, 0]}>
            <boxGeometry args={[s.w, 0.1, 0.74]} />
            <meshStandardMaterial {...top} />
          </mesh>
        </group>
      ))}
    </group>
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

/* Restrained instanced ground detail: grass tufts, bushes, rocks. */
function GroundDetail({ sites, minX, maxX }: { sites: number[]; minX: number; maxX: number }) {
  const grass = useRef<THREE.InstancedMesh>(null);
  const bush = useRef<THREE.InstancedMesh>(null);
  const rocks = useRef<THREE.InstancedMesh>(null);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const col = useMemo(() => new THREE.Color(), []);

  useLayoutEffect(() => {
    const clearOfPads = (x: number, z: number) =>
      !nearPad(x, z, sites, 8.2) && z > -22 && z < 10;
    let gi = 0, bi = 0, ri = 0;
    const GN = 340, BN = 34, RN = 64;
    for (let i = 0; i < 900 && (gi < GN || bi < BN || ri < RN); i++) {
      const x = minX + hash(i, 1) * (maxX - minX);
      const z = -22 + hash(i, 2) * 32;
      if (!clearOfPads(x, z)) continue;
      const y = groundH(x, z);
      const pick = hash(i, 3);
      if (pick < 0.72 && gi < GN) {
        dummy.position.set(x, y + 0.2, z);
        dummy.rotation.set(0, hash(i, 4) * Math.PI, 0);
        const s = 0.7 + hash(i, 5) * 0.9;
        dummy.scale.set(s, s * (0.8 + hash(i, 6) * 0.7), s);
        dummy.updateMatrix();
        grass.current?.setMatrixAt(gi, dummy.matrix);
        grass.current?.setColorAt(gi, col.set(hash(i, 7) > 0.5 ? COLORS.grass : COLORS.grassDark));
        gi++;
      } else if (pick < 0.86 && bi < BN) {
        dummy.position.set(x, y + 0.25, z);
        dummy.rotation.set(0, hash(i, 8) * Math.PI, 0);
        const s = 0.6 + hash(i, 9) * 1.1;
        dummy.scale.set(s, s * 0.55, s);
        dummy.updateMatrix();
        bush.current?.setMatrixAt(bi, dummy.matrix);
        bush.current?.setColorAt(bi, col.set(COLORS.grassDark).multiplyScalar(0.8 + hash(i, 10) * 0.4));
        bi++;
      } else if (ri < RN) {
        dummy.position.set(x, y + 0.08, z);
        dummy.rotation.set(hash(i, 11) * 3, hash(i, 12) * 3, 0);
        const s = 0.5 + hash(i, 13) * 1.2;
        dummy.scale.set(s, s * 0.7, s);
        dummy.updateMatrix();
        rocks.current?.setMatrixAt(ri, dummy.matrix);
        rocks.current?.setColorAt(ri, col.set(hash(i, 14) > 0.5 ? COLORS.rock : COLORS.gravel));
        ri++;
      }
    }
    for (const [m, n] of [[grass.current, gi], [bush.current, bi], [rocks.current, ri]] as const) {
      if (!m) continue;
      m.count = n;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
  }, [sites, minX, maxX, dummy, col]);

  return (
    <group>
      <instancedMesh ref={grass} args={[undefined, undefined, 340]} frustumCulled={false}>
        <coneGeometry args={[0.1, 0.55, 5]} />
        <meshStandardMaterial roughness={1} />
      </instancedMesh>
      <instancedMesh ref={bush} args={[undefined, undefined, 34]} castShadow frustumCulled={false}>
        <icosahedronGeometry args={[0.55, 1]} />
        <meshStandardMaterial roughness={1} flatShading />
      </instancedMesh>
      <instancedMesh ref={rocks} args={[undefined, undefined, 64]} castShadow frustumCulled={false}>
        <dodecahedronGeometry args={[0.24, 0]} />
        <meshStandardMaterial roughness={0.9} flatShading />
      </instancedMesh>
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
  const minX = sorted[0] - 16;
  const maxX = sorted[sorted.length - 1] + 16;
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
      <DisplacedPlane cx={midX} cz={-13} w={fullW} d={20} sites={sites} />
      <DisplacedPlane cx={midX} cz={6.5} w={fullW} d={7} sites={sites} />
      {/* Shaft strip segments with openings */}
      {strips.map((s, i) => (
        <DisplacedPlane key={i} cx={s.cx} cz={0} w={s.w} d={6} sites={sites} />
      ))}
      <GroundDetail sites={sites} minX={minX} maxX={maxX} />
      {/* Shaft walls + floor per site */}
      {sites.map((sx, i) => (
        <group key={sx} position={[sx, 0, 0]}>
          <WellPad x={0.8} />
          <ExcavationRim hw={hw} />
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
