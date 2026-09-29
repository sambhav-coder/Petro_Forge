"use client";

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { COLORS, LAYOUT, thermalVisual } from "@/lib/scene";
import { useSelectable } from "@/lib/useSelectable";
import type { SceneSelection, TwinSnapshot } from "@/lib/types";

const COUNT = 220;

function ThermalParticles({ thermal, bounds }: { thermal: number; bounds: number }) {
  const ref = useRef<THREE.Points>(null);
  const { positions, speeds } = useMemo(() => {
    const positions = new Float32Array(COUNT * 3);
    const speeds = new Float32Array(COUNT);
    // Deterministic lattice placement — no Math.random.
    for (let i = 0; i < COUNT; i++) {
      const a = (i * 2.399963) % (Math.PI * 2);
      const r = bounds * Math.sqrt(((i * 37) % 100) / 100);
      positions[i * 3] = Math.cos(a) * r;
      positions[i * 3 + 1] =
        LAYOUT.reservoirBottom + ((i * 53) % 100) / 100 * (LAYOUT.reservoirTop - LAYOUT.reservoirBottom);
      positions[i * 3 + 2] = Math.sin(a) * r * 0.7;
      speeds[i] = 0.5 + ((i * 13) % 10) / 14;
    }
    return { positions, speeds };
  }, [bounds]);

  useFrame((_, dt) => {
    const pts = ref.current;
    if (!pts) return;
    const arr = (pts.geometry.attributes.position as THREE.BufferAttribute).array as Float32Array;
    const rise = dt * (0.25 + thermal * 1.6);
    for (let i = 0; i < COUNT; i++) {
      arr[i * 3 + 1] += rise * speeds[i];
      if (arr[i * 3 + 1] > LAYOUT.reservoirTop) arr[i * 3 + 1] = LAYOUT.reservoirBottom;
    }
    pts.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color={COLORS.heatHot}
        size={0.14}
        transparent
        opacity={0.18 + thermal * 0.55}
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
}: {
  wellId: string;
  twin: TwinSnapshot | null;
  selection: SceneSelection | null;
  onSelect: (s: SceneSelection) => void;
}) {
  const { selected, hovered, handlers } = useSelectable(
    "reservoir",
    wellId,
    `Reservoir — ${wellId}`,
    selection,
    onSelect
  );
  const glowRef = useRef<THREE.MeshStandardMaterial>(null);
  const thermal = twin
    ? thermalVisual(twin.estimated_temperature_c, twin.baseline_reservoir_temperature_c)
    : 0.15;

  // GPU-uniform pulse — no React re-render per frame.
  useFrame(({ clock }) => {
    const m = glowRef.current;
    if (!m) return;
    const p = (Math.sin(clock.elapsedTime * 1.4) + 1) / 2;
    m.emissiveIntensity = 0.35 + thermal * 1.5 + p * 0.12 * thermal;
  });

  const w = LAYOUT.shaftHalfWidth * 2 - 0.4;
  const h = LAYOUT.reservoirTop - LAYOUT.reservoirBottom;
  const cy = (LAYOUT.reservoirTop + LAYOUT.reservoirBottom) / 2;

  return (
    <group {...handlers}>
      {/* Cap rock + base rock bands */}
      <mesh position={[0, LAYOUT.reservoirTop + 0.7, 0]}>
        <boxGeometry args={[w, 1.4, 5.6]} />
        <meshStandardMaterial color={COLORS.sandstoneDeep} roughness={0.9} />
      </mesh>
      <mesh position={[0, LAYOUT.reservoirBottom - 0.7, 0]}>
        <boxGeometry args={[w, 1.4, 5.6]} />
        <meshStandardMaterial color="#241b10" roughness={1} />
      </mesh>
      {/* Oil-bearing sandstone volume */}
      <mesh position={[0, cy, 0]}>
        <boxGeometry args={[w, h, 5.4]} />
        <meshStandardMaterial
          color={COLORS.sandstone}
          transparent
          opacity={0.5}
          roughness={0.75}
          emissive={COLORS.oilDeep}
          emissiveIntensity={0.15 + thermal * 0.5}
        />
      </mesh>
      {/* Thermal influence zone (visual mapping of scalar twin temperature) */}
      <mesh position={[0, cy, 0]}>
        <boxGeometry args={[w * 0.62, h * 0.8, 3.4]} />
        <meshStandardMaterial
          ref={glowRef}
          color={COLORS.oilAmber}
          transparent
          opacity={0.12 + thermal * 0.4}
          roughness={0.4}
          emissive={COLORS.heatHot}
          emissiveIntensity={0.5}
          depthWrite={false}
        />
      </mesh>
      {/* Selection shell (visual-only; hidden when idle). */}
      <mesh position={[0, cy, 0]} visible={selected || hovered}>
        <boxGeometry args={[w + 0.25, h + 0.4, 5.65]} />
        <meshBasicMaterial
          color={COLORS.selectTeal}
          transparent
          opacity={selected ? 0.22 : hovered ? 0.1 : 0}
          depthWrite={false}
        />
      </mesh>
      <ThermalParticles thermal={thermal} bounds={w * 0.3} />
      {hovered && !selected && (
        <Html position={[0, LAYOUT.reservoirTop + 2.2, 0]} center>
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
            Reservoir — {wellId}
            {twin ? ` · ${twin.estimated_temperature_c.toFixed(1)} °C` : ""}
          </div>
        </Html>
      )}
    </group>
  );
}
