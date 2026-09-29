"use client";

import { Canvas } from "@react-three/fiber";
import { ContactShadows, Stars } from "@react-three/drei";
import { COLORS, LAYOUT } from "@/lib/scene";
import type { CameraPreset, IsolatableKind, SceneSelection, TwinSnapshot, ViewMode, WellSummary } from "@/lib/types";
import Terrain from "./Terrain";
import WellAssembly from "./WellAssembly";
import CameraRig from "./CameraRig";
import PressureOverlay, { PRESSURE_OVERLAY_ENABLED } from "./PressureOverlay";

export default function FieldScene({
  wells,
  twins,
  selection,
  onSelect,
  onDeselect,
  preset,
  focusWellId,
  viewMode,
  isolated,
}: {
  wells: WellSummary[];
  twins: Record<string, TwinSnapshot>;
  selection: SceneSelection | null;
  onSelect: (s: SceneSelection) => void;
  onDeselect: () => void;
  preset: CameraPreset;
  focusWellId: string | null;
  viewMode: ViewMode;
  isolated: IsolatableKind | null;
}) {
  const sites = wells.map((_, i) => i * LAYOUT.wellSpacing);
  const focusIdx = Math.max(
    wells.findIndex((w) => w.well_id === (focusWellId ?? selection?.wellId)),
    0
  );
  const focusX = sites[focusIdx] ?? 0;
  const selIdx = Math.max(
    wells.findIndex((w) => w.well_id === selection?.wellId),
    focusIdx
  );

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: [24, 15, 30], fov: 46, near: 0.5, far: 400 }}
      gl={{ antialias: true }}
      onPointerMissed={() => onDeselect()}
    >
      <color attach="background" args={[COLORS.bg]} />
      <fogExp2 attach="fog" args={[COLORS.bg, 0.011]} />

      {/* Cinematic industrial lighting */}
      <ambientLight intensity={0.28} />
      <hemisphereLight args={["#24314f", "#1a1208", 0.55]} />
      <directionalLight
        position={[16, 26, 12]}
        intensity={2.1}
        color="#fff1d6"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-30}
        shadow-camera-right={30}
        shadow-camera-top={30}
        shadow-camera-bottom={-35}
      />
      <directionalLight position={[-14, 8, -16]} intensity={0.65} color={COLORS.selectTeal} />
      <pointLight position={[focusX, -20, 4]} intensity={14} distance={22} color={COLORS.oilAmber} />

      <Stars radius={140} depth={40} count={2200} factor={3.2} saturation={0} fade speed={0.4} />
      <ContactShadows position={[focusX, 0.02, 0]} scale={46} blur={2.4} opacity={0.55} far={12} />

      <Terrain sites={sites} selectedWellIndex={selIdx} viewMode={viewMode} />
      {wells.map((w, i) => (
        <WellAssembly
          key={w.well_id}
          x={sites[i]}
          wellId={w.well_id}
          twin={twins[w.well_id] ?? null}
          selection={selection}
          onSelect={onSelect}
          viewMode={viewMode}
          isolated={selection?.wellId === w.well_id ? isolated : null}
        />
      ))}
      <CameraRig preset={preset} focusX={focusX} />
      {PRESSURE_OVERLAY_ENABLED && focusWellId && (
        <PressureOverlay wellId={focusWellId} twin={twins[focusWellId] ?? null} visible />
      )}
    </Canvas>
  );
}
