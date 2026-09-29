"use client";

import { useState } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import type { ObjectKind, SceneSelection } from "@/lib/types";

interface Handlers {
  onClick: (e: ThreeEvent<MouseEvent>) => void;
  onPointerOver: (e: ThreeEvent<PointerEvent>) => void;
  onPointerOut: (e: ThreeEvent<PointerEvent>) => void;
}

export function useSelectable(
  kind: ObjectKind,
  wellId: string,
  label: string,
  selection: SceneSelection | null,
  onSelect: (s: SceneSelection) => void
): { hovered: boolean; selected: boolean; handlers: Handlers } {
  const [hovered, setHovered] = useState(false);
  const selected = selection?.kind === kind && selection?.wellId === wellId;
  return {
    hovered,
    selected,
    handlers: {
      onClick: (e) => {
        e.stopPropagation();
        onSelect({ kind, wellId, label });
      },
      onPointerOver: (e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      },
      onPointerOut: () => {
        setHovered(false);
        document.body.style.cursor = "auto";
      },
    },
  };
}

/** Emissive tint for hover / selection states (sophisticated, not neon). */
export function selectEmissive(
  selected: boolean,
  hovered: boolean,
  base = "#000000"
): { emissive: string; emissiveIntensity: number } {
  if (selected) return { emissive: "#2dd4bf", emissiveIntensity: 0.38 };
  if (hovered) return { emissive: "#2dd4bf", emissiveIntensity: 0.14 };
  return { emissive: base, emissiveIntensity: 0 };
}
