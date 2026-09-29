"use client";

import { useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { COLORS, LAYOUT } from "@/lib/scene";
import { useSelectable } from "@/lib/useSelectable";
import { useKindIsolation } from "@/lib/useIsolation";
import type { IsolatableKind, ObjectKind, SceneSelection, TwinSnapshot, ViewMode } from "@/lib/types";
import Reservoir from "./Reservoir";

/* Prototype SRP assembly — stylized geometry (relative units).
   No real dimensions, depths, or equipment specs are claimed. */

function Part({
  kind,
  wellId,
  label,
  selection,
  onSelect,
  shellPos,
  shellSize,
  children,
}: {
  kind: ObjectKind;
  wellId: string;
  label: string;
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
      {/* Highlight shell is visual-only: hidden when idle so it never
          intercepts pointer events meant for neighboring objects. */}
      <mesh position={shellPos} visible={selected || hovered} userData={{ noDim: true }}>
        <boxGeometry args={shellSize} />
        <meshBasicMaterial
          color={COLORS.selectTeal}
          transparent
          opacity={selected ? 0.16 : hovered ? 0.07 : 0}
          depthWrite={false}
        />
      </mesh>
      {hovered && !selected && (
        <Html position={[shellPos[0], shellPos[1] + shellSize[1] / 2 + 0.4, shellPos[2]]} center>
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
            {label}
          </div>
        </Html>
      )}
    </group>
  );
}

function FlowPulses({ active }: { active: boolean }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    if (!active) return;
    const t = clock.elapsedTime * 0.55;
    refs.current.forEach((m, i) => {
      if (!m) return;
      const f = (t + i / 3) % 1;
      m.position.set(0.9 + f * 2.6, 0.9, 0);
      m.visible = true;
    });
  });
  if (!active) return null;
  return (
    <group>
      {[0, 1, 2].map((i) => (
        <mesh key={i} ref={(m) => { refs.current[i] = m; }}>
          <sphereGeometry args={[0.13, 12, 12]} />
          <meshStandardMaterial
            color={COLORS.oilAmber}
            emissive={COLORS.oilAmber}
            emissiveIntensity={1.6}
          />
        </mesh>
      ))}
    </group>
  );
}

export default function WellAssembly({
  x,
  wellId,
  twin,
  selection,
  onSelect,
  viewMode,
  isolated,
}: {
  x: number;
  wellId: string;
  twin: TwinSnapshot | null;
  selection: SceneSelection | null;
  onSelect: (s: SceneSelection) => void;
  viewMode: ViewMode;
  isolated: IsolatableKind | null;
}) {
  const beam = useRef<THREE.Group>(null);
  const crank = useRef<THREE.Mesh>(null);
  const rodGroup = useRef<THREE.Group>(null);
  const root = useRef<THREE.Group>(null);
  useKindIsolation(root, isolated, viewMode);

  const spm = twin?.spm ?? 0;
  const producing = (twin?.estimated_oil_production_bopd ?? 0) > 0.01;
  const pumpY = LAYOUT.pumpY;

  // Controlled transparency per view mode (engineering readability).
  const casingOpacity = viewMode === "NORMAL" ? 0.55 : viewMode === "CUTAWAY" ? 0.32 : 0.15;
  const tubingOpacity = viewMode === "NORMAL" ? 0.88 : viewMode === "CUTAWAY" ? 0.95 : 0.5;

  useFrame(({ clock }) => {
    const running = spm > 0;
    const omega = running ? (spm * Math.PI * 2) / 60 : 0;
    const phase = clock.elapsedTime * omega;
    const swing = running ? Math.sin(phase) : 0;
    if (beam.current) beam.current.rotation.z = swing * 0.13;
    if (crank.current) crank.current.rotation.z = running ? -phase : 0.6;
    if (rodGroup.current) rodGroup.current.position.y = running ? swing * 0.5 : 0;
  });

  const steel = { color: COLORS.steel, metalness: 0.85, roughness: 0.35 };
  const steelDark = { color: COLORS.steelDark, metalness: 0.8, roughness: 0.5 };

  return (
    <group position={[x, 0, 0]} ref={root}>
      {/* Equipment sits on the compacted gravel pad built by Terrain. */}

      {/* Well label */}
      <Html position={[0, 8.2, 0]} center>
        <div
          style={{
            fontSize: 12,
            fontFamily: "monospace",
            fontWeight: 700,
            background: "rgba(7,11,20,0.85)",
            border: "1px solid rgba(245,165,36,0.4)",
            borderRadius: 6,
            padding: "4px 10px",
            color: "#fcd34d",
            whiteSpace: "nowrap",
          }}
        >
          {wellId}
          {twin ? ` · ${twin.css_phase} · ${twin.estimated_oil_production_bopd.toFixed(1)} BOPD` : ""}
        </div>
      </Html>

      {/* ============ WELLHEAD ============ */}
      <Part kind="wellhead" wellId={wellId} label={`Wellhead — ${wellId}`}
        selection={selection} onSelect={onSelect}
        shellPos={[0, 1, 0]} shellSize={[2.8, 2.6, 2.4]}>
        <mesh position={[0, 0.42, 0]} castShadow>
          <cylinderGeometry args={[1.0, 1.1, 0.35, 24]} />
          <meshStandardMaterial {...steelDark} />
        </mesh>
        <mesh position={[0, 1.0, 0]} castShadow>
          <cylinderGeometry args={[0.7, 0.7, 0.9, 24]} />
          <meshStandardMaterial {...steel} />
        </mesh>
        <mesh position={[0, 1.6, 0]} castShadow>
          <cylinderGeometry args={[0.95, 0.95, 0.3, 24]} />
          <meshStandardMaterial {...steelDark} />
        </mesh>
        <mesh position={[0, 1.05, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.2, 0.2, 1.7, 16]} />
          <meshStandardMaterial {...steel} />
        </mesh>
        {[-0.7, 0.7].map((dx) => (
          <group key={dx}>
            <mesh position={[dx, 1.35, 0]} castShadow>
              <cylinderGeometry args={[0.12, 0.12, 0.5, 12]} />
              <meshStandardMaterial {...steelDark} />
            </mesh>
            <mesh position={[dx, 1.65, 0]}>
              <boxGeometry args={[0.34, 0.1, 0.34]} />
              <meshStandardMaterial color={COLORS.warn} metalness={0.6} roughness={0.4} />
            </mesh>
          </group>
        ))}
        {/* Outlet pipe to separator tank */}
        <mesh position={[2.0, 0.9, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.18, 0.18, 2.6, 14]} />
          <meshStandardMaterial {...steel} />
        </mesh>
        <mesh position={[4.6, 0.95, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
          <cylinderGeometry args={[0.9, 0.9, 3.0, 20]} />
          <meshStandardMaterial color="#4d5a70" metalness={0.75} roughness={0.4} />
        </mesh>
        {[-1.1, 1.1].map((dx) => (
          <mesh key={dx} position={[4.6 + dx, 0.3, 0]}>
            <boxGeometry args={[0.25, 0.7, 1.2]} />
            <meshStandardMaterial color={COLORS.steelDark} metalness={0.6} roughness={0.6} />
          </mesh>
        ))}
      </Part>
      <FlowPulses active={producing} />

      {/* ============ SRP SURFACE UNIT ============ */}
      <Part kind="srp" wellId={wellId} label={`SRP surface unit — ${wellId} (motion follows SPM)`}
        selection={selection} onSelect={onSelect}
        shellPos={[3.2, 2.8, 0]} shellSize={[9.5, 6.2, 3.6]}>
        {/* A-frame legs */}
        {[-1.0, 1.0].map((dz) => (
          <mesh key={dz} position={[3.4, 2.4, dz]} rotation={[0, 0, -0.18]} castShadow>
            <boxGeometry args={[0.5, 4.9, 0.5]} />
            <meshStandardMaterial color="#7a2e2e" metalness={0.6} roughness={0.5} />
          </mesh>
        ))}
        {/* Walking beam (animated) */}
        <group position={[3.4, 4.7, 0]}>
          <group ref={beam}>
            <mesh position={[-0.25, 0, 0]} castShadow>
              <boxGeometry args={[7.6, 0.55, 0.7]} />
              <meshStandardMaterial color="#8a3434" metalness={0.65} roughness={0.45} />
            </mesh>
            {/* Horsehead over the wellhead */}
            <mesh position={[-3.65, -0.55, 0]} castShadow>
              <cylinderGeometry args={[1.0, 1.0, 0.75, 20]} />
              <meshStandardMaterial color="#6e2828" metalness={0.6} roughness={0.5} />
            </mesh>
          </group>
        </group>
        {/* Crank + counterweight (animated) */}
        <mesh ref={crank} position={[6.6, 2.1, 0]} castShadow>
          <cylinderGeometry args={[0.95, 0.95, 0.42, 24]} />
          <meshStandardMaterial {...steelDark} />
        </mesh>
        <mesh position={[6.6, 2.1, 0.35]}>
          <boxGeometry args={[0.7, 1.3, 0.18]} />
          <meshStandardMaterial color="#8a3434" metalness={0.6} roughness={0.5} />
        </mesh>
        {/* Pitman arm (static link approximation) */}
        <mesh position={[5.9, 3.3, 0]} rotation={[0, 0, 0.35]}>
          <boxGeometry args={[0.22, 2.6, 0.22]} />
          <meshStandardMaterial {...steel} />
        </mesh>
        {/* Motor */}
        <mesh position={[6.6, 0.75, 2.3]} castShadow>
          <boxGeometry args={[1.7, 1.2, 1.2]} />
          <meshStandardMaterial color="#2f4a5a" metalness={0.7} roughness={0.4} />
        </mesh>
      </Part>

      {/* Polished rod + rod string (animated with SPM) */}
      <group ref={rodGroup}>
        <Part kind="rod" wellId={wellId} label={`Rod string — ${wellId}`}
          selection={selection} onSelect={onSelect}
          shellPos={[0, -8, 0]} shellSize={[0.9, 25, 0.9]}>
          <mesh position={[0, 2.6, 0]}>
            <cylinderGeometry args={[0.09, 0.09, 3.4, 12]} />
            <meshStandardMaterial color="#d7dee9" metalness={1} roughness={0.12} />
          </mesh>
          <mesh position={[0, -9.1, 0]}>
            <cylinderGeometry args={[0.12, 0.12, 21.6, 12]} />
            <meshStandardMaterial color={COLORS.rodMetal} metalness={1} roughness={0.18} />
          </mesh>
        </Part>
      </group>

      {/* ============ CASING (own entity) ============ */}
      <Part kind="casing" wellId={wellId} label={`Casing — ${wellId}`}
        selection={selection} onSelect={onSelect}
        shellPos={[0, -8.2, 0]} shellSize={[1.7, 18.5, 1.7]}>
        <mesh position={[0, -8.2, 0]}>
          <cylinderGeometry args={[0.55, 0.55, 17.6, 20, 1, true]} />
          <meshStandardMaterial color={COLORS.casing} metalness={0.7} roughness={0.45}
            transparent opacity={casingOpacity} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>
      </Part>

      {/* ============ TUBING (own entity) ============ */}
      <Part kind="tubing" wellId={wellId} label={`Production tubing — ${wellId}`}
        selection={selection} onSelect={onSelect}
        shellPos={[0, -9.6, 0]} shellSize={[1.1, 21.5, 1.1]}>
        <mesh position={[0, -9.6, 0]}>
          <cylinderGeometry args={[0.32, 0.32, 20.8, 16]} />
          {/* Slight transparency so the inner rod string reads in cutaway. */}
          <meshStandardMaterial color="#c8d2e0" metalness={0.95} roughness={0.22}
            transparent opacity={tubingOpacity} />
        </mesh>
      </Part>

      {/* ============ DOWNHOLE PUMP ============ */}
      <Part kind="pump" wellId={wellId} label={`Downhole pump — ${wellId}`}
        selection={selection} onSelect={onSelect}
        shellPos={[0, pumpY, 0]} shellSize={[1.8, 3.6, 1.8]}>
        <mesh position={[0, pumpY, 0]} castShadow>
          <cylinderGeometry args={[0.45, 0.45, 2.4, 18]} />
          <meshStandardMaterial
            color="#7c8aa0" metalness={0.85} roughness={0.3}
            emissive={producing ? COLORS.oilAmber : "#000000"}
            emissiveIntensity={producing ? 0.3 : 0}
          />
        </mesh>
        {[-0.8, 0.8].map((dy) => (
          <mesh key={dy} position={[0, pumpY + dy, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.45, 0.08, 10, 24]} />
            <meshStandardMaterial {...steelDark} />
          </mesh>
        ))}
        <mesh position={[0, pumpY - 1.5, 0]}>
          <cylinderGeometry args={[0.3, 0.22, 0.7, 14]} />
          <meshStandardMaterial {...steelDark} />
        </mesh>
      </Part>

      {/* Reservoir volume for this well */}
      <Reservoir wellId={wellId} twin={twin} selection={selection} onSelect={onSelect} viewMode={viewMode} />
    </group>
  );
}
