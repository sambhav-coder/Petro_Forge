"use client";

import { useEffect, useRef, useState } from "react";

/* Six engineering modules — dark cinematic containers with bespoke
 * miniature visualizations. Structural/conceptual content only:
 * no fabricated measurements, no fake predictions. */

function useInView<T extends HTMLElement>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        if (e.isIntersecting) { setInView(true); io.unobserve(e.target); }
      }),
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, inView];
}

function Shell({
  index, kicker, title, body, footnote, children, wide,
}: {
  index: number; kicker: string; title: string; body: string;
  footnote: string; children: React.ReactNode; wide?: boolean;
}) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`card-enter ${inView ? "in-view" : ""} ${wide ? "md:col-span-2" : ""}`}
      style={{ transitionDelay: `${(index % 3) * 80}ms` }}>
      <article className="group relative h-full overflow-hidden rounded-2xl border border-natural/12
        bg-gradient-to-b from-forest-deep/50 to-oil-black/90 p-6 md:p-7
        hover:border-natural/28 transition-colors duration-500
        hover:shadow-[0_10px_60px_rgba(63,166,107,0.09)]">
        {/* grid texture */}
        <div aria-hidden="true" className="absolute inset-0 opacity-[0.5]" style={{
          backgroundImage: "linear-gradient(rgba(63,166,107,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(63,166,107,0.05) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
          maskImage: "radial-gradient(ellipse 90% 80% at 50% 20%, black 30%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse 90% 80% at 50% 20%, black 30%, transparent 75%)",
        }} />
        <div className="relative">
          <div className="text-[9.5px] font-mono font-semibold tracking-[0.28em] text-natural/70 mb-2">{kicker}</div>
          <h3 className="font-display font-semibold tracking-[0.03em] text-[clamp(1.15rem,2vw,1.5rem)] text-cream-soft leading-snug">{title}</h3>
          <p className="mt-2 text-[12px] leading-relaxed text-sand/60 max-w-prose">{body}</p>
          <div className="mt-5">{children}</div>
          <div className="mt-5 pt-3 border-t border-natural/10 text-[9.5px] font-mono tracking-[0.14em] text-sand/40 uppercase">{footnote}</div>
        </div>
      </article>
    </div>
  );
}

/* ---- 1 · WELL-TO-SURFACE (wide): pumpjack silhouette + lift path ---- */
function WellToSurfaceViz() {
  return (
    <svg viewBox="0 0 640 190" className="w-full h-auto" role="img" aria-label="Reservoir to wellbore to SRP to surface flow">
      {/* pay zone */}
      <rect x="20" y="120" width="150" height="46" rx="6" fill="rgba(122,82,52,0.25)" stroke="rgba(122,82,52,0.6)" />
      <text x="34" y="140" fontSize="10" fill="#C6A878" fontFamily="JetBrains Mono, monospace" letterSpacing="2">RESERVOIR</text>
      <text x="34" y="155" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace">pay · heavy oil</text>
      {/* wellbore */}
      <rect x="230" y="30" width="26" height="136" fill="rgba(198,168,120,0.08)" stroke="rgba(198,168,120,0.4)" />
      <line x1="243" y1="30" x2="243" y2="166" stroke="#3FA66B" strokeWidth="2" strokeDasharray="5 4" className="flow-diagram" />
      <text x="222" y="182" fontSize="10" fill="#C6A878" fontFamily="JetBrains Mono, monospace" letterSpacing="2">WELLBORE</text>
      {/* pumpjack silhouette */}
      <g stroke="#C6A878" strokeWidth="2" fill="none" opacity="0.9">
        <line x1="380" y1="166" x2="430" y2="70" />
        <line x1="430" y1="70" x2="520" y2="86" />
        <line x1="430" y1="70" x2="430" y2="166" />
        <line x1="400" y1="166" x2="460" y2="166" />
        <circle cx="430" cy="70" r="4" fill="#D99A3D" stroke="none" />
        <line x1="505" y1="86" x2="505" y2="130" stroke="#D99A3D" />
      </g>
      <text x="392" y="182" fontSize="10" fill="#3FA66B" fontFamily="JetBrains Mono, monospace" letterSpacing="2">SRP UNIT</text>
      {/* surface */}
      <rect x="548" y="110" width="72" height="56" rx="6" fill="rgba(63,166,107,0.1)" stroke="rgba(63,166,107,0.5)" />
      <text x="556" y="133" fontSize="10" fill="#3FA66B" fontFamily="JetBrains Mono, monospace" letterSpacing="1">SURFACE</text>
      <text x="556" y="148" fontSize="9" fill="rgba(63,166,107,0.7)" fontFamily="JetBrains Mono, monospace">metering</text>
      {/* connectors */}
      <line x1="170" y1="143" x2="230" y2="143" stroke="#3FA66B" strokeWidth="1.4" />
      <polyline points="164,139 172,143 164,147" fill="none" stroke="#3FA66B" strokeWidth="1.4" />
      <line x1="256" y1="100" x2="380" y2="100" stroke="rgba(63,166,107,0.6)" strokeWidth="1.4" strokeDasharray="5 4" className="flow-diagram" />
      <line x1="460" y1="120" x2="548" y2="130" stroke="rgba(63,166,107,0.6)" strokeWidth="1.4" />
      <polyline points="542,126 550,130 542,134" fill="none" stroke="#3FA66B" strokeWidth="1.4" />
      {/* depth ticks */}
      {[40, 80, 120, 160].map((y) => (
        <g key={y}>
          <line x1="20" y1={y} x2="28" y2={y} stroke="rgba(198,168,120,0.4)" />
          <text x="284" y={y + 3} fontSize="8" fill="rgba(198,168,120,0.45)" fontFamily="JetBrains Mono, monospace">{166 - y}m</text>
        </g>
      ))}
    </svg>
  );
}

/* ---- 2 · CSS INTELLIGENCE: steam cascade with rising wisps ---- */
function CssViz() {
  return (
    <div className="relative">
      <div aria-hidden="true" className="absolute left-[52px] top-2 bottom-2 w-px bg-gradient-to-b from-amber-warm/60 via-amber-warm/25 to-natural/50" />
      <div aria-hidden="true" className="steam-wisp left-[46px] top-6" />
      <div aria-hidden="true" className="steam-wisp left-[56px] top-2" style={{ animationDelay: "1.4s" }} />
      <div className="space-y-3 relative">
        {[
          { t: "STEAM", s: "injection · soak", c: "amber" },
          { t: "HEAT", s: "thermal front spreads", c: "amber" },
          { t: "VISCOSITY ↓", s: "μ collapses with T", c: "sand" },
          { t: "MOBILITY ↑", s: "oil begins to move", c: "green" },
          { t: "PRODUCTION", s: "SOR + energy metered", c: "green" },
        ].map((n) => (
          <div key={n.t} className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full shrink-0 ml-[48px] ${
              n.c === "amber" ? "bg-amber-warm shadow-[0_0_10px_rgba(217,154,61,0.7)]"
              : n.c === "green" ? "bg-natural shadow-[0_0_10px_rgba(63,166,107,0.7)]"
              : "bg-sand/80"}`} />
            <div>
              <div className="text-[11px] font-mono font-bold tracking-[0.14em] text-cream-soft">{n.t}</div>
              <div className="text-[10px] font-mono text-sand/50">{n.s}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- 3 · SRP: stroke waveform + rod load ---- */
function SrpViz() {
  return (
    <svg viewBox="0 0 320 150" className="w-full h-auto" role="img" aria-label="Stroke waveform and rod load curve">
      <text x="4" y="14" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace" letterSpacing="2">STROKE</text>
      <path d="M 4 44 Q 44 10, 84 44 T 164 44 T 244 44 T 316 44" fill="none" stroke="#D99A3D" strokeWidth="1.8"
        strokeDasharray="6 4" className="flow-diagram" />
      <text x="4" y="86" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace" letterSpacing="2">ROD LOAD</text>
      <path d="M 4 116 Q 60 116, 90 96 T 170 108 T 260 92 T 316 100" fill="none" stroke="#3FA66B" strokeWidth="1.8" />
      <circle cx="260" cy="92" r="3.5" fill="#D99A3D" />
      <text x="268" y="88" fontSize="8.5" fill="#D99A3D" fontFamily="JetBrains Mono, monospace">peak</text>
      {/* SPM bar */}
      <rect x="4" y="130" width="200" height="7" rx="3.5" fill="rgba(198,168,120,0.12)" />
      <rect x="4" y="130" width="118" height="7" rx="3.5" fill="rgba(63,166,107,0.7)" />
      <text x="210" y="137" fontSize="9" fill="rgba(232,221,200,0.7)" fontFamily="JetBrains Mono, monospace">SPM · stroke · fillage</text>
    </svg>
  );
}

/* ---- 4 · ML: conceptual pattern, explicitly non-predictive ---- */
function MlViz() {
  const pts: [number, number][] = [[20, 110], [52, 102], [84, 96], [116, 90], [148, 84], [180, 78], [212, 74]];
  return (
    <svg viewBox="0 0 320 150" className="w-full h-auto" role="img" aria-label="Conceptual ML pattern: history, trend, anomaly, forecast zone">
      {/* forecast zone */}
      <rect x="228" y="10" width="88" height="120" fill="rgba(217,154,61,0.07)" stroke="rgba(217,154,61,0.35)" strokeDasharray="4 3" />
      <text x="236" y="24" fontSize="8.5" fill="rgba(217,154,61,0.8)" fontFamily="JetBrains Mono, monospace">FORECAST</text>
      {/* history + trend */}
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill="rgba(63,166,107,0.85)" />
      ))}
      <line x1="20" y1="110" x2="228" y2="66" stroke="rgba(63,166,107,0.6)" strokeWidth="1.4" strokeDasharray="5 4" className="flow-diagram" />
      {/* anomaly */}
      <circle cx="148" cy="84" r="7" fill="none" stroke="#D99A3D" strokeWidth="1.4" strokeDasharray="3 2" />
      <circle cx="148" cy="84" r="3" fill="#D99A3D" />
      <text x="120" y="140" fontSize="8.5" fill="rgba(217,154,61,0.8)" fontFamily="JetBrains Mono, monospace">anomaly flagged</text>
      <text x="20" y="140" fontSize="8.5" fill="rgba(198,168,120,0.55)" fontFamily="JetBrains Mono, monospace">history → trend</text>
    </svg>
  );
}

/* ---- 5 · PHYSICS: relationship chips + viscosity curve ---- */
function PhysicsViz() {
  return (
    <div>
      <svg viewBox="0 0 320 110" className="w-full h-auto" role="img" aria-label="Viscosity falls as temperature rises">
        <text x="4" y="14" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace" letterSpacing="2">μ (T) ↓</text>
        <path d="M 30 100 C 90 96, 140 70, 200 34 S 280 12, 312 10" fill="none" stroke="#D99A3D" strokeWidth="1.8" />
        <text x="236" y="100" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace">T →</text>
      </svg>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {["T(t) thermal", "μ(T) viscosity", "q inflow", "Q pump", "SOR · kWh"].map((c) => (
          <span key={c} className="px-2 py-1 rounded-md border border-natural/20 bg-natural/8 text-[9.5px] font-mono text-natural/90">{c}</span>
        ))}
      </div>
      <div className="mt-2 text-[10px] font-mono text-sand/50">production = min(inflow, pump) · solved, not guessed</div>
    </div>
  );
}

/* ---- 6 · OPTIMIZATION (wide): candidates + constraint + selection ---- */
function OptViz() {
  const cand: [number, number, boolean][] = [
    [60, 120, false], [110, 100, false], [160, 108, false], [210, 84, false],
    [260, 92, false], [310, 70, false], [360, 78, false], [410, 60, true],
    [460, 66, false], [500, 52, false], [150, 130, false], [330, 110, false],
  ];
  return (
    <svg viewBox="0 0 640 170" className="w-full h-auto" role="img" aria-label="Candidate operating points with constraint boundary and selected region">
      <text x="8" y="16" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace" letterSpacing="2">SOR ↓</text>
      {/* constraint boundary */}
      <path d="M 30 150 C 200 130, 400 90, 610 30" fill="none" stroke="rgba(217,154,61,0.6)" strokeWidth="1.4" strokeDasharray="6 4" />
      <text x="480" y="46" fontSize="9" fill="rgba(217,154,61,0.8)" fontFamily="JetBrains Mono, monospace">constraint boundary</text>
      {/* selected region */}
      <ellipse cx="410" cy="62" rx="52" ry="30" fill="rgba(63,166,107,0.1)" stroke="rgba(63,166,107,0.55)" strokeDasharray="4 3" />
      <text x="368" y="106" fontSize="9" fill="#3FA66B" fontFamily="JetBrains Mono, monospace">SELECTED</text>
      {cand.map(([x, y, best], i) => (
        <circle key={i} cx={x} cy={y} r={best ? 5 : 3}
          fill={best ? "#D99A3D" : "rgba(63,166,107,0.65)"}
          stroke={best ? "#E8DDC8" : "none"} strokeWidth={best ? 1.2 : 0} />
      ))}
      <text x="8" y="162" fontSize="9" fill="rgba(198,168,120,0.6)" fontFamily="JetBrains Mono, monospace">PRODUCTION →</text>
    </svg>
  );
}

export default function StoryModules() {
  return (
    <div className="grid gap-5 md:gap-6 grid-cols-1 md:grid-cols-2">
      <Shell index={0} wide kicker="01 · COUPLED SYSTEM" title="Well-to-surface, one model"
        body="Steam changes what the reservoir can deliver; the pump can only lift what arrives. PetroForge solves both sides together — inflow and lift, heat and steel."
        footnote="Backend → twin_physics · coupled production">
        <WellToSurfaceViz />
      </Shell>
      <Shell index={1} kicker="02 · THERMAL PROCESS" title="CSS intelligence"
        body="Injection, soak, production, cut-off — heat is tracked as a thermal front that collapses viscosity and unlocks mobility."
        footnote="Backend → CSS cycle engine">
        <CssViz />
      </Shell>
      <Shell index={2} kicker="03 · LIFT" title="SRP / pump intelligence"
        body="Stroke, SPM and fillage set the mechanical ceiling. Rod loading and impact risk are scored against inflow on every snapshot."
        footnote="Backend → pump capacity · risk proxies">
        <SrpViz />
      </Shell>
      <Shell index={3} kicker="04 · ML INTELLIGENCE" title="Forecasts only when honest"
        body="Forecasting, anomaly and health models arm only on sufficient labeled history. Insufficient data renders as an explicit state — never a fabricated 0% risk."
        footnote="Backend → ML registry · conceptual pattern shown">
        <MlViz />
      </Shell>
      <Shell index={4} kicker="05 · DETERMINISTIC ENGINE" title="Solved equations"
        body="Thermal response, viscosity, inflow, pump capacity, SOR and energy are closed-form prototype physics — every twin number traces to an equation."
        footnote="Backend → twin_physics">
        <PhysicsViz />
      </Shell>
      <Shell index={5} wide kicker="06 · DECISION" title="Constrained optimization"
        body="A 243-scenario grid over steam, soak, SPM and stroke searches production against SOR, energy and mechanical risk — returning the recommended point with its reasons."
        footnote="Backend → grid optimizer · top-5 + why_recommended">
        <OptViz />
      </Shell>
    </div>
  );
}
