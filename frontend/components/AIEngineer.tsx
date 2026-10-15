"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type * as THREE from "three";

/* Realistic-leaning procedural petroleum engineer (PPE: hard hat, hi-vis vest).
   Honest placeholder pipeline: no licensed GLB is bundled (see docs); if
   NEXT_PUBLIC_COPILOT_AVATAR_URL points at a licensed GLB it can replace this
   group via <primitive>. Geometry here is schematic, NOT a measured human. */

export type EngineerMode = "idle" | "listening" | "explaining" | "speaking";

export default function AIEngineer({
  mode = "idle",
  position = [0, 0, 0] as [number, number, number],
  reduceMotion = false,
}: {
  mode?: EngineerMode;
  position?: [number, number, number];
  reduceMotion?: boolean;
}) {
  const root = useRef<THREE.Group>(null);
  const head = useRef<THREE.Group>(null);
  const jaw = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    if (reduceMotion || !root.current) return;
    const t = clock.getElapsedTime();
    const amp = mode === "speaking" ? 1 : mode === "explaining" ? 0.7 : mode === "listening" ? 0.35 : 0.25;
    root.current.position.y = position[1] + Math.sin(t * 1.6) * 0.03 * amp;
    root.current.rotation.y = Math.sin(t * 0.5) * 0.12 * amp;
    if (head.current) {
      head.current.rotation.x = Math.sin(t * (mode === "speaking" ? 5 : 1.2)) * 0.05 * amp;
      head.current.rotation.y = Math.sin(t * 0.8) * 0.18 * amp;
    }
    if (jaw.current) {
      const open = mode === "speaking" ? Math.abs(Math.sin(t * 7)) * 0.05 : 0;
      jaw.current.position.y = -0.16 - open;
      jaw.current.scale.y = 1 + open * 8;
    }
  });

  const visor = mode === "listening" ? "#2dd4bf" : mode === "speaking" ? "#f5a524" : "#9aa7b8";

  return (
    <group ref={root} position={position}>
      {/* legs */}
      <mesh position={[-0.14, 0.45, 0]} castShadow>
        <cylinderGeometry args={[0.09, 0.11, 0.9, 12]} />
        <meshStandardMaterial color="#232b38" roughness={0.8} />
      </mesh>
      <mesh position={[0.14, 0.45, 0]} castShadow>
        <cylinderGeometry args={[0.09, 0.11, 0.9, 12]} />
        <meshStandardMaterial color="#232b38" roughness={0.8} />
      </mesh>
      {/* torso + hi-vis vest */}
      <mesh position={[0, 1.15, 0]} castShadow>
        <cylinderGeometry args={[0.26, 0.3, 0.85, 16]} />
        <meshStandardMaterial color="#c96a1e" roughness={0.65} />
      </mesh>
      <mesh position={[0, 1.22, 0.01]}>
        <cylinderGeometry args={[0.275, 0.29, 0.3, 16]} />
        <meshStandardMaterial color="#d8e14a" emissive="#5a6208" emissiveIntensity={0.35} roughness={0.5} />
      </mesh>
      {/* arms */}
      <mesh position={[-0.36, 1.15, 0.05]} rotation={[0.2, 0, 0.35]} castShadow>
        <cylinderGeometry args={[0.07, 0.08, 0.7, 10]} />
        <meshStandardMaterial color="#8a5a24" roughness={0.7} />
      </mesh>
      <mesh position={[0.36, 1.15, 0.05]} rotation={[mode === "explaining" ? -0.9 : 0.2, 0, -0.35]} castShadow>
        <cylinderGeometry args={[0.07, 0.08, 0.7, 10]} />
        <meshStandardMaterial color="#8a5a24" roughness={0.7} />
      </mesh>
      {/* head group */}
      <group ref={head} position={[0, 1.85, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.21, 24, 18]} />
          <meshStandardMaterial color="#b98a5e" roughness={0.55} />
        </mesh>
        {/* jaw (lip-sync proxy) */}
        <mesh ref={jaw} position={[0, -0.16, 0.1]}>
          <boxGeometry args={[0.12, 0.03, 0.05]} />
          <meshStandardMaterial color="#7a5238" roughness={0.7} />
        </mesh>
        {/* safety glasses visor tint by mode */}
        <mesh position={[0, 0.02, 0.18]}>
          <boxGeometry args={[0.3, 0.07, 0.02]} />
          <meshStandardMaterial color={visor} transparent opacity={0.75} roughness={0.2} />
        </mesh>
        {/* hard hat */}
        <mesh position={[0, 0.17, 0]} castShadow>
          <sphereGeometry args={[0.24, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#e8b81e" roughness={0.4} />
        </mesh>
        <mesh position={[0, 0.17, 0]}>
          <cylinderGeometry args={[0.3, 0.3, 0.04, 24]} />
          <meshStandardMaterial color="#d1a317" roughness={0.45} />
        </mesh>
        {/* headlamp */}
        <mesh position={[0, 0.2, 0.24]}>
          <boxGeometry args={[0.08, 0.06, 0.03]} />
          <meshStandardMaterial color="#222" emissive="#fff2c0" emissiveIntensity={mode === "speaking" ? 1.2 : 0.5} />
        </mesh>
      </group>
      {/* status ring */}
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.5, 0.58, 40]} />
        <meshBasicMaterial color={mode === "speaking" ? "#f5a524" : mode === "listening" ? "#2dd4bf" : "#3a4354"} transparent opacity={0.85} />
      </mesh>
    </group>
  );
}

/** Non-WebGL fallback: neutral avatar-unavailable card (never a fake 3D claim). */
export function EngineerFallback({ mode }: { mode: EngineerMode }) {
  return (
    <div className="rounded-xl border border-natural/20 bg-oil-black/70 p-3 text-center" role="status">
      <div className="text-2xl" aria-hidden="true">👷</div>
      <div className="text-[10px] font-mono tracking-[0.15em] uppercase text-sand/60">
        AI Engineer · {mode} · 3D unavailable
      </div>
      <div className="text-[10px] font-mono text-sand/40 mt-1">
        Analysis continues in text mode. Procedural 3D placeholder only — no licensed avatar bundled.
      </div>
    </div>
  );
}
