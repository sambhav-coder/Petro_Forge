"use client";

import { useMemo } from "react";
import * as THREE from "three";

/*
 * Controlled ambient environment: gradient sky dome + distant ridge
 * silhouettes + warm horizon. Replaces the "infinite space" feel with
 * an earth / industrial-site atmosphere. Stylized — no geographic claim.
 */

function SkyDome() {
  const mat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        fog: false,
        uniforms: {
          top: { value: new THREE.Color("#04060c") },
          mid: { value: new THREE.Color("#0b1220") },
          horizon: { value: new THREE.Color("#4a3220") },
        },
        vertexShader: `
          varying vec3 vPos;
          void main() {
            vPos = position;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: `
          uniform vec3 top; uniform vec3 mid; uniform vec3 horizon;
          varying vec3 vPos;
          void main() {
            float h = normalize(vPos).y;
            vec3 c = h > 0.25
              ? mix(mid, top, smoothstep(0.25, 0.9, h))
              : mix(horizon, mid, smoothstep(-0.05, 0.25, h));
            // Warm glow band just above the horizon, strongest toward -Z.
            float band = exp(-abs(h - 0.03) * 14.0);
            c += vec3(0.45, 0.22, 0.08) * band * 0.55;
            gl_FragColor = vec4(c, 1.0);
          }
        `,
      }),
    []
  );
  return (
    <mesh material={mat} renderOrder={-10}>
      <sphereGeometry args={[220, 24, 16]} />
    </mesh>
  );
}

function Ridges() {
  const ridges = useMemo(
    () =>
      [
        { x: -70, z: -110, r: 55, h: 13, c: "#141a26" },
        { x: 10, z: -125, r: 70, h: 17, c: "#100f16" },
        { x: 90, z: -105, r: 48, h: 11, c: "#161a24" },
        { x: -120, z: -40, r: 50, h: 12, c: "#12161f" },
        { x: 125, z: -30, r: 52, h: 10, c: "#12161f" },
      ] as const,
    []
  );
  return (
    <group>
      {ridges.map((r, i) => (
        <mesh key={i} position={[r.x, -1, r.z]}>
          <coneGeometry args={[r.r, r.h, 7]} />
          <meshStandardMaterial color={r.c} roughness={1} flatShading />
        </mesh>
      ))}
    </group>
  );
}

export default function Environment() {
  return (
    <group>
      <SkyDome />
      <Ridges />
    </group>
  );
}
