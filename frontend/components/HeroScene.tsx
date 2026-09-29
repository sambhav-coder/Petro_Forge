"use client";

import { useRef } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { COLORS } from "@/lib/scene";

/*
 * Lightweight landing-page preview: a stylized well + thermal reservoir
 * with slow camera drift. Decorative only — NOT the full twin scene,
 * makes no API calls, shows no engineering numbers.
 */

function MiniWell() {
  const glow = useRef<THREE.MeshStandardMaterial>(null);
  const beam = useRef<THREE.Group>(null);
  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    if (glow.current) glow.current.emissiveIntensity = 0.7 + ((Math.sin(t * 1.3) + 1) / 2) * 0.7;
    if (beam.current) beam.current.rotation.z = Math.sin(t * 1.1) * 0.12;
  });
  return (
    <group>
      {/* Ground disc */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -3.4, 0]} receiveShadow>
        <circleGeometry args={[7.5, 40]} />
        <meshStandardMaterial color="#3a2f22" roughness={1} />
      </mesh>
      {/* Wellbore line into reservoir */}
      <mesh position={[0, -1.4, 0]}>
        <cylinderGeometry args={[0.16, 0.16, 4.4, 10]} />
        <meshStandardMaterial color="#c8d2e0" metalness={0.9} roughness={0.3} />
      </mesh>
      {/* Wellhead */}
      <mesh position={[0, 0.9, 0]}>
        <cylinderGeometry args={[0.55, 0.65, 0.8, 16]} />
        <meshStandardMaterial color="#8b98ac" metalness={0.8} roughness={0.35} />
      </mesh>
      {/* Mini beam unit */}
      <group position={[1.6, 2.4, 0]}>
        <group ref={beam}>
          <mesh position={[-0.2, 0, 0]}>
            <boxGeometry args={[3.6, 0.28, 0.36]} />
            <meshStandardMaterial color="#8a3434" metalness={0.6} roughness={0.5} />
          </mesh>
        </group>
        <mesh position={[0, -1.2, 0]}>
          <boxGeometry args={[0.3, 2.4, 0.3]} />
          <meshStandardMaterial color="#5b2333" metalness={0.6} roughness={0.5} />
        </mesh>
      </group>
      {/* Reservoir glow volume */}
      <mesh position={[0, -2.6, 0]}>
        <boxGeometry args={[4.6, 1.5, 3.2]} />
        <meshStandardMaterial
          ref={glow}
          color={COLORS.oilAmber}
          transparent
          opacity={0.5}
          emissive={COLORS.heatHot}
          emissiveIntensity={0.8}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

export default function HeroScene() {
  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [9, 4.5, 11], fov: 42, near: 0.5, far: 200 }}
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#0a0f1a"]} />
      <fog attach="fog" args={["#0a0f1a", 18, 46]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[8, 12, 6]} intensity={1.8} color="#ffe7c4" />
      <directionalLight position={[-8, 4, -8]} intensity={0.5} color="#2dd4bf" />
      <pointLight position={[0, -2.6, 2]} intensity={8} distance={12} color={COLORS.oilAmber} />
      <MiniWell />
      <OrbitControls
        enableZoom={false}
        enablePan={false}
        autoRotate
        autoRotateSpeed={0.7}
        maxPolarAngle={Math.PI * 0.55}
        minPolarAngle={Math.PI * 0.2}
      />
    </Canvas>
  );
}
