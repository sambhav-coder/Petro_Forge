"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { CameraPreset } from "@/lib/types";

function desiredFor(preset: CameraPreset, focusX: number): { pos: THREE.Vector3; tgt: THREE.Vector3 } {
  if (preset === "WELL")
    return {
      pos: new THREE.Vector3(focusX + 8.5, 6.5, 11),
      tgt: new THREE.Vector3(focusX, -1.5, 0),
    };
  if (preset === "RESERVOIR")
    return {
      pos: new THREE.Vector3(focusX + 9.5, -12.5, 13),
      tgt: new THREE.Vector3(focusX, -20, 0),
    };
  return {
    pos: new THREE.Vector3(focusX * 0.3 + 24, 15, 30),
    tgt: new THREE.Vector3(focusX * 0.3, -7, 0),
  };
}

export default function CameraRig({
  preset,
  focusX,
}: {
  preset: CameraPreset;
  focusX: number;
}) {
  const controls = useRef<OrbitControlsImpl>(null);
  const anim = useRef<{ t: number; active: boolean }>({ t: 0, active: true });
  const from = useRef<{ pos: THREE.Vector3; tgt: THREE.Vector3 } | null>(null);
  const { camera } = useThree();

  useEffect(() => {
    from.current = {
      pos: camera.position.clone(),
      tgt: controls.current?.target.clone() ?? new THREE.Vector3(),
    };
    anim.current = { t: 0, active: true };
  }, [preset, focusX, camera]);

  useFrame((_, rawDt) => {
    const c = controls.current;
    if (!c) return;
    const dt = Math.min(rawDt, 0.05);
    if (anim.current.active && from.current) {
      anim.current.t += dt;
      const k = Math.min(anim.current.t / 1.4, 1);
      const e = 1 - Math.pow(1 - k, 3); // ease-out cubic
      const want = desiredFor(preset, focusX);
      camera.position.lerpVectors(from.current.pos, want.pos, e);
      c.target.lerpVectors(from.current.tgt, want.tgt, e);
      if (k >= 1) anim.current.active = false;
    }
    c.update();
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={4}
      maxDistance={90}
      maxPolarAngle={Math.PI * 0.62}
      onStart={() => {
        anim.current.active = false;
      }}
    />
  );
}
