"use client";

/*
 * PetroForge mark: hexagonal forge/metal geometry + PF monogram.
 * Pure inline SVG — no image dependency. Works in header + landing.
 */
export default function Logo({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-label="PetroForge">
      <defs>
        <linearGradient id="pf-metal" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#9aa7b8" />
          <stop offset="55%" stopColor="#5b6b82" />
          <stop offset="100%" stopColor="#3a4354" />
        </linearGradient>
        <linearGradient id="pf-earth" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4ade80" />
          <stop offset="100%" stopColor="#1d3a2a" />
        </linearGradient>
      </defs>
      <polygon
        points="24,3 42,13.5 42,34.5 24,45 6,34.5 6,13.5"
        fill="url(#pf-metal)"
        stroke="#d6b98c"
        strokeWidth="1.6"
      />
      <polygon
        points="24,9 36.5,16.2 36.5,31.8 24,39 11.5,31.8 11.5,16.2"
        fill="#0d1f16"
      />
      <text
        x="24"
        y="30.5"
        textAnchor="middle"
        fontFamily="Inter, system-ui, sans-serif"
        fontWeight="800"
        fontSize="15"
        fill="url(#pf-earth)"
      >
        PF
      </text>
      <rect x="14" y="34.5" width="20" height="2.2" rx="1.1" fill="#f5a524" opacity="0.85" />
    </svg>
  );
}
