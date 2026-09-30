"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

interface LogoProps {
  size?: number;
  showText?: boolean;
  animated?: boolean;
  className?: string;
}

/**
 * PetroForge Logo component.
 *
 * Priority:
 *  1. User-supplied logo image (petroforge-logo.svg or the supplied JPG)
 *  2. Inline SVG fallback with the PF monogram + hexagonal frame
 *
 * Animations (respects prefers-reduced-motion):
 *  - subtle breathing/glow opacity modulation
 *  - very slow vertical float
 *  - occasional soft light sweep
 *  - slight filter glow variation
 */
export default function Logo({
  size = 36,
  showText = false,
  animated = true,
  className = "",
}: LogoProps) {
  const [reducedMotion, setReducedMotion] = useState(false);
  const [useImage, setUseImage] = useState(true);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const set = () => setReducedMotion(mq.matches);
    set();
    mq.addEventListener?.("change", set);
    return () => mq.removeEventListener?.("change", set);
  }, []);

  const animClasses = animated && !reducedMotion
    ? "animate-breathe animate-floatSlow"
    : "";

  return (
    <div
      className={`inline-flex items-center gap-3 ${className}`}
      style={{ pointerEvents: "none" }}
    >
      <div
        className={`relative logo-sweep ${animClasses}`}
        style={{ width: size, height: size, flexShrink: 0 }}
        aria-label="PetroForge logo"
        role="img"
      >
        {useImage ? (
          <Image
            ref={imgRef as never}
            src="/photo_2026-09-30_12-05-46.jpg"
            alt="PetroForge"
            width={size}
            height={size}
            style={{
              width: size,
              height: size,
              objectFit: "contain",
              filter:
                "drop-shadow(0 0 10px rgba(63,166,107,0.25)) drop-shadow(0 0 4px rgba(217,154,61,0.15))",
            }}
            onError={() => setUseImage(false)}
            priority
          />
        ) : (
          <LogoSVG size={size} />
        )}
      </div>

      {showText && (
        <div className="leading-none tracking-[0.18em]">
          <span className="font-display font-bold text-[0.92em] text-sand">
            PETRO
          </span>
          <span className="font-display font-bold text-[0.92em] text-natural">
            FORGE
          </span>
        </div>
      )}
    </div>
  );
}

/* Fallback inline SVG — hexagonal forge/metal geometry + PF monogram. */
function LogoSVG({ size }: { size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      style={{
        filter:
          "drop-shadow(0 0 10px rgba(63,166,107,0.3)) drop-shadow(0 0 4px rgba(217,154,61,0.2))",
      }}
    >
      <defs>
        <linearGradient id="pf-metal-2" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#C6A878" />
          <stop offset="50%" stopColor="#7A5234" />
          <stop offset="100%" stopColor="#5A3A24" />
        </linearGradient>
        <linearGradient id="pf-earth-2" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3FA66B" />
          <stop offset="60%" stopColor="#1F6B45" />
          <stop offset="100%" stopColor="#0B241A" />
        </linearGradient>
        <radialGradient id="pf-inner-glow" cx="0.5" cy="0.45" r="0.65">
          <stop offset="0%" stopColor="#123F2A" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#07100D" stopOpacity="1" />
        </radialGradient>
      </defs>

      {/* Outer hexagonal frame */}
      <polygon
        points="24,3 42,13.5 42,34.5 24,45 6,34.5 6,13.5"
        fill="url(#pf-metal-2)"
        stroke="#C6A878"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      {/* Inner face with subtle radial glow */}
      <polygon
        points="24,8.5 37,16.2 37,31.8 24,39.5 11,31.8 11,16.2"
        fill="url(#pf-inner-glow)"
        stroke="#1F6B45"
        strokeOpacity="0.45"
        strokeWidth="0.8"
      />
      {/* PF monogram */}
      <text
        x="24"
        y="30.5"
        textAnchor="middle"
        fontFamily="'Space Grotesk', Inter, system-ui, sans-serif"
        fontWeight="700"
        fontSize="14.5"
        letterSpacing="-0.5"
        fill="url(#pf-earth-2)"
      >
        PF
      </text>
      {/* Amber forge base line */}
      <rect
        x="13.5"
        y="34.8"
        width="21"
        height="2"
        rx="1"
        fill="#D99A3D"
        opacity="0.9"
      />
    </svg>
  );
}
