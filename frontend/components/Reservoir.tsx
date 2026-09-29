"use client";

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { COLORS, LAYOUT, thermalVisual } from "@/lib/scene";
import { useSelectable } from "@/lib/useSelectable";
import type { ObjectKind, SceneSelection, TwinSnapshot, ViewMode } from "@/lib/types";

const COUNT = 220;

function Tip({ text }: { text: string }) {
  return (
    <div
      style={{
        fontSize: 11,
        fontFamily: "monospace",
        background: "rgba(7,11,20,0.9)",
        border: "1px solid #2dd4bf55",
        borderRadius: 6,
        padding: "4px 8px",
        color: "#99f6e4",
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </div>
  );
}

/* Selectable geological layer with component-kind tagging for isolation. */
function Layer({
  kind,
  label,
  tip,
  wellId,
  selection,
  onSelect,
  shellPos,
  shellSize,
  children,
}: {
  kind: ObjectKind;
  label: string;
  tip: string;
  wellId: string;
  selection: SceneSelection | null;
  onSelect: (s: SceneSelection) => void;
  shellPos: [number, number, number];
  shellSize: [number, number, number];
  children: React.ReactNode;
}) {
  const { hovered, selected, handlers } = useSelectable(kind, wellId, label, selection, onSelect);
  return (
    <group {...handlers} userData={{ componentKind: kind }}>
      {children}
      <mesh position={shellPos} visible={selected || hovered} userData={{ noDim: true }}>
        <boxGeometry args={shellSize} />
        <meshBasicMaterial
          color={COLORS.selectTeal}
          transparent
          opacity={selected ? 0.2 : 0.08}
          depthWrite={false}
        />
      </mesh>
      {hovered && !selected && (
        <Html position={[shellPos[0], shellPos[1] + shellSize[1] / 2 + 0.4, shellPos[2]]} center>
          <Tip text={tip} />
        </Html>
      )}
    </group>
  );
}

function ThermalParticles({
  live,
  bounds,
}: {
  live: React.RefObject<{ v: number }>;
  bounds: number;
}) {
  const ref = useRef<THREE.Points>(null);
  const mat = useRef<THREE.PointsMaterial>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(COUNT * 3);
    // Deterministic lattice placement — no Math.random.
    for (let i = 0; i < COUNT; i++) {
      const a = (i * 2.399963) % (Math.PI * 2);
      const r = bounds * Math.sqrt(((i * 37) % 100) / 100);
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] =
        LAYOUT.reservoirBottom + ((i * 53) % 100) / 100 * (LAYOUT.reservoirTop - LAYOUT.reservoirBottom);
      arr[i * 3 + 2] = Math.sin(a) * r * 0.7;
    }
    return arr;
  }, [bounds]);
  const speeds = useMemo(() => {
    const s = new Float32Array(COUNT);
    for (let i = 0; i < COUNT; i++) s[i] = 0.5 + ((i * 13) % 10) / 14;
    return s;
  }, []);

  useFrame((_, dt) => {
    const pts = ref.current;
    if (!pts) return;
    const v = live.current?.v ?? 0.15;
    const arr = (pts.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array;
    const rise = Math.min(dt, 0.05) * (0.25 + v * 1.6);
    for (let i = 0; i < COUNT; i++) {
      arr[i * 3 + 1] += rise * speeds[i];
      if (arr[i * 3 + 1] > LAYOUT.reservoirTop) arr[i * 3 + 1] = LAYOUT.reservoirBottom;
    }
    pts.geometry.attributes.position.needsUpdate = true;
    if (mat.current) mat.current.opacity = 0.18 + v * 0.55;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        ref={mat}
        color={COLORS.heatHot}
        size={0.14}
        transparent
        opacity={0.3}
        depthWrite={false}
      />
    </points>
  );
}

export default function Reservoir({
  wellId,
  twin,
  selection,
  onSelect,
  viewMode,
}: {
  wellId: string;
  twin: TwinSnapshot | null;
  selection: SceneSelection | null;
  onSelect: (s: SceneSelection) => void;
  viewMode: ViewMode;
}) {
  const glowRef = useRef<THREE.MeshStandardMaterial>(null);
  const zoneRef = useRef<THREE.Group>(null);
  const thermalTarget = twin
    ? thermalVisual(twin.estimated_temperature_c, twin.baseline_reservoir_temperature_c)
    : 0.15;
  // Damped transition: well switches glide the visual state instead of jumping.
  const live = useRef({ v: 0.15 });

  useFrame(({ clock }, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const r = live.current;
    r.v += (thermalTarget - r.v) * Math.min(1, dt * 2.2);
    const p = (Math.sin(clock.elapsedTime * 1.4) + 1) / 2;
    if (glowRef.current) {
      glowRef.current.emissiveIntensity = 0.35 + r.v * 1.5 + p * 0.12 * r.v;
      glowRef.current.opacity = 0.12 + r.v * 0.4;
    }
    if (zoneRef.current) {
      const s = 0.62 + 0.38 * r.v; // cooler twin → smaller/subtler zone
      zoneRef.current.scale.set(s, 1, s);
    }
  });

  const w = LAYOUT.shaftHalfWidth * 2 - 0.4;
  const h = LAYOUT.reservoirTop - LAYOUT.reservoirBottom;
  const cy = (LAYOUT.reservoirTop + LAYOUT.reservoirBottom) / 2;
  const rockOpacity = viewMode === "NORMAL" ? 1 : viewMode === "CUTAWAY" ? 0.35 : 0.1;
  const oilOpacity = viewMode === "NORMAL" ? 0.5 : viewMode === "CUTAWAY" ? 0.35 : 0.18;

  return (
    <group>
      {/* 1. Cap rock (formation layer) */}
      <Layer kind="formation" label={`Cap rock — ${wellId}`} tip={`Cap rock — ${wellId} (structural)`}
        wellId={wellId} selection={selection} onSelect={onSelect}
        shellPos={[0, LAYOUT.reservoirTop + 0.7, 0]} shellSize={[w + 0.2, 1.8, 5.8]}>
        <mesh position={[0, LAYOUT.reservoirTop + 0.7, 0]}>
          <boxGeometry args={[w, 1.4, 5.6]} />
          <meshStandardMaterial color={COLORS.sandstoneDeep} roughness={0.9}
            transparent opacity={rockOpacity} />
        </mesh>
      </Layer>

      {/* 4. Base rock (formation layer) */}
      <Layer kind="formation" label={`Base rock — ${wellId}`} tip={`Base rock — ${wellId} (structural)`}
        wellId={wellId} selection={selection} onSelect={onSelect}
        shellPos={[0, LAYOUT.reservoirBottom - 0.7, 0]} shellSize={[w + 0.2, 1.8, 5.8]}>
        <mesh position={[0, LAYOUT.reservoirBottom - 0.7, 0]}>
          <boxGeometry args={[w, 1.4, 5.6]} />
          <meshStandardMaterial color="#241b10" roughness={1}
            transparent opacity={rockOpacity} />
        </mesh>
      </Layer>

      {/* 2. Heavy-oil bearing zone */}
      <Layer kind="reservoir" label={`Oil-bearing zone — ${wellId}`}
        tip={`Oil zone — ${wellId}${twin ? ` · ${twin.estimated_temperature_c.toFixed(1)} °C` : ""}`}
        wellId={wellId} selection={selection} onSelect={onSelect}
        shellPos={[0, cy, 0]} shellSize={[w + 0.25, h + 0.4, 5.65]}>
        <mesh position={[0, cy, 0]}>
          <boxGeometry args={[w, h, 5.4]} />
          <meshStandardMaterial
            color={COLORS.sandstone}
            transparent
            opacity={oilOpacity}
            roughness={0.75}
            emissive={COLORS.oilDeep}
            emissiveIntensity={0.15 + thermalTarget * 0.5}
          />
        </mesh>
      </Layer>

      {/* 3. Thermal influence zone — scalar twin mapping, not a solver */}
      <Layer kind="thermal" label={`Thermal zone — ${wellId}`}
        tip={`Thermal zone — ${wellId} (twin scalar visual)`}
        wellId={wellId} selection={selection} onSelect={onSelect}
        shellPos={[0, cy, 0]} shellSize={[w * 0.62 + 0.25, h * 0.8 + 0.3, 3.65]}>
        <group ref={zoneRef}>
          <mesh position={[0, cy, 0]}>
            <boxGeometry args={[w * 0.62, h * 0.8, 3.4]} />
            <meshStandardMaterial
              ref={glowRef}
              color={COLORS.oilAmber}
              transparent
              opacity={0.3}
              roughness={0.4}
              emissive={COLORS.heatHot}
              emissiveIntensity={0.5}
              depthWrite={false}
            />
          </mesh>
          <ThermalParticles live={live} bounds={w * 0.3} />
        </group>
        <Html position={[0, LAYOUT.reservoirTop + 2.4, 0]} center>
          <div
            style={{
              fontSize: 9,
              fontFamily: "monospace",
              color: "#b45309",
              background: "rgba(7,11,20,0.75)",
              border: "1px solid #b4530955",
              borderRadius: 5,
              padding: "2px 7px",
              whiteSpace: "nowrap",
            }}
          >
            THERMAL STATE — VISUALIZED FROM TWIN SCALAR
          </div>
        </Html>
      </Layer>
    </group>
  );
}
