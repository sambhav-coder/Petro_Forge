"use client";

import { useEffect, useState } from "react";

/* Central engineering visualization: how PetroForge understands a well.
 * Conceptual system diagram — structural labels only, no fabricated
 * measurements. Particles use SMIL animateMotion, gated on reduced-motion. */

type Node = {
  id: string;
  y: number;
  tone: "green" | "amber" | "sand" | "brown";
  title: string;
  sub: string;
  side?: string;
};

const CX = 210;
const NODES: Node[] = [
  { id: "res", y: 56, tone: "brown", title: "RESERVOIR", sub: "Jodhpur Sand · heavy oil", side: "PAY ZONE" },
  { id: "thm", y: 152, tone: "amber", title: "THERMAL STATE", sub: "steam heat · soak", side: "ΔT" },
  { id: "vis", y: 248, tone: "amber", title: "VISCOSITY", sub: "μ falls with heat", side: "cP ↓" },
  { id: "mob", y: 344, tone: "green", title: "MOBILITY", sub: "inflow unlocks", side: "λ ↑" },
  { id: "inf", y: 440, tone: "green", title: "INFLOW", sub: "reservoir delivers q", side: "bopd" },
  { id: "wbr", y: 536, tone: "sand", title: "WELLBORE", sub: "lift path · drawdown", side: "ΔP" },
  { id: "srp", y: 632, tone: "green", title: "SRP / PUMP", sub: "SPM × stroke × fillage", side: "spm" },
  { id: "sur", y: 728, tone: "sand", title: "SURFACE", sub: "wellhead · metering", side: "bar" },
  { id: "prd", y: 824, tone: "green", title: "PRODUCTION", sub: "min(inflow, pump)", side: "SOR · kWh" },
  { id: "opt", y: 920, tone: "amber", title: "OPTIMIZATION", sub: "243-scenario search", side: "BEST" },
];

const TONE = {
  green: { stroke: "#3FA66B", glow: "rgba(63,166,107,0.35)", fill: "#0B241A" },
  amber: { stroke: "#D99A3D", glow: "rgba(217,154,61,0.35)", fill: "#1a1208" },
  sand: { stroke: "#C6A878", glow: "rgba(198,168,120,0.3)", fill: "#12100b" },
  brown: { stroke: "#7A5234", glow: "rgba(122,82,52,0.4)", fill: "#120c07" },
} as const;

const SPINE = `M ${CX} 56 ${[...NODES.slice(1).map((n) => `L ${CX} ${n.y}`)].join(" ")}`;
const BRANCH = `M ${CX} 56 C ${CX - 130} 120, ${CX - 130} 300, ${CX} 440`;

function Particle({
  path,
  dur,
  begin,
  color,
  reduced,
}: {
  path: string;
  dur: string;
  begin: string;
  color: string;
  reduced: boolean;
}) {
  if (reduced) return <circle cx={CX} cy={440} r={2.5} fill={color} opacity={0.7} />;
  return (
    <circle r={3} fill={color} opacity={0.95}>
      <animateMotion dur={dur} begin={begin} repeatCount="indefinite" path={path} />
    </circle>
  );
}

export default function SystemFlow() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return (
    <div className="relative w-full max-w-[560px] mx-auto" role="img"
      aria-label="System diagram: reservoir, thermal state, viscosity, mobility, inflow, wellbore, SRP pump, surface, production, optimization">
      {/* coordinate ticks */}
      <div aria-hidden="true" className="absolute left-0 top-4 bottom-4 hidden sm:flex flex-col justify-between text-[8.5px] font-mono text-sand/30">
        {["+1150m", "+800m", "+400m", "0m · WH"].map((t) => (
          <span key={t} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-px bg-sand/25" />{t}
          </span>
        ))}
      </div>

      <svg viewBox="0 0 420 985" className="w-full h-auto" aria-hidden="true">
        <defs>
          <linearGradient id="spine-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7A5234" />
            <stop offset="35%" stopColor="#D99A3D" />
            <stop offset="65%" stopColor="#3FA66B" />
            <stop offset="100%" stopColor="#D99A3D" />
          </linearGradient>
          <filter id="node-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* pressure branch (right side feed into INFLOW) */}
        <path d={BRANCH} fill="none" stroke="rgba(198,168,120,0.4)" strokeWidth="1.2"
          strokeDasharray="5 4" className={reduced ? "" : "flow-diagram"} />
        <path d={`M ${CX} 56 C ${CX + 130} 140, ${CX + 130} 300, ${CX} 440`} fill="none"
          stroke="rgba(63,166,107,0.35)" strokeWidth="1.2" strokeDasharray="5 4"
          className={reduced ? "" : "flow-diagram"} />

        {/* main spine */}
        <path d={SPINE} fill="none" stroke="url(#spine-grad)" strokeWidth="1.6" opacity="0.85" />

        {/* branch label */}
        <text x={CX + 96} y={240} fontSize="9" fill="rgba(198,168,120,0.6)"
          fontFamily="JetBrains Mono, monospace" letterSpacing="2">PRESSURE</text>
        <text x={CX - 172} y={240} fontSize="9" fill="rgba(217,154,61,0.65)"
          fontFamily="JetBrains Mono, monospace" letterSpacing="2">THERMAL</text>

        {/* traveling particles */}
        <Particle reduced={reduced} path={SPINE} dur="11s" begin="0s" color="#3FA66B" />
        <Particle reduced={reduced} path={SPINE} dur="11s" begin="-5.5s" color="#D99A3D" />
        <Particle reduced={reduced} path={BRANCH} dur="7s" begin="-2s" color="#D99A3D" />
        <Particle reduced={reduced} path={`M ${CX} 56 C ${CX + 130} 140, ${CX + 130} 300, ${CX} 440`}
          dur="8s" begin="-4s" color="#3FA66B" />

        {/* nodes */}
        {NODES.map((n) => {
          const t = TONE[n.tone];
          return (
            <g key={n.id}>
              <circle cx={CX} cy={n.y} r={13} fill={t.fill} stroke={t.stroke}
                strokeWidth="1.6" filter="url(#node-glow)" className={reduced ? "" : "node-pulse"} />
              <circle cx={CX} cy={n.y} r={4.5} fill={t.stroke} opacity="0.9" />
              {/* label plate */}
              <rect x={CX + 26} y={n.y - 20} width={150} height={40} rx={7}
                fill="rgba(7,16,13,0.82)" stroke="rgba(198,168,120,0.22)" strokeWidth="1" />
              <text x={CX + 38} y={n.y - 3} fontSize="12.5" fontWeight="700" fill="#E8DDC8"
                fontFamily="Space Grotesk, Inter, sans-serif" letterSpacing="1.5">{n.title}</text>
              <text x={CX + 38} y={n.y + 12} fontSize="9.5" fill="rgba(198,168,120,0.65)"
                fontFamily="JetBrains Mono, monospace">{n.sub}</text>
              {/* side annotation */}
              {n.side && (
                <text x={CX - 34} y={n.y + 3.5} fontSize="9" textAnchor="end"
                  fill={t.stroke} opacity="0.85" fontFamily="JetBrains Mono, monospace"
                  letterSpacing="1">{n.side}</text>
              )}
            </g>
          );
        })}

        {/* production sparkline */}
        <polyline points="248,806 262,812 276,803 290,809 304,800 318,805 332,798"
          fill="none" stroke="#3FA66B" strokeWidth="1.4" opacity="0.9" />
        {/* optimization candidates */}
        {[[262, 906], [282, 912], [300, 904], [318, 910], [292, 922]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i === 2 ? 4 : 2.2}
            fill={i === 2 ? "#D99A3D" : "rgba(63,166,107,0.7)"}
            opacity={i === 2 ? 1 : 0.6} />
        ))}
        {/* reservoir strata */}
        {[30, 44, 70, 84].map((y) => (
          <line key={y} x1={CX - 150} y1={y} x2={CX + 150} y2={y}
            stroke="rgba(122,82,52,0.5)" strokeWidth="1" strokeDasharray="2 5" />
        ))}
      </svg>
    </div>
  );
}
