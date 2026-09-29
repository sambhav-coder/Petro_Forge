import dynamic from "next/dynamic";
import Link from "next/link";
import Logo from "@/components/Logo";

const HeroScene = dynamic(() => import("@/components/HeroScene"), { ssr: false });

function SectionTitle({ kicker, title }: { kicker: string; title: string }) {
  return (
    <div className="mb-8">
      <div className="text-[11px] font-mono font-bold tracking-[0.25em] text-leaf">{kicker}</div>
      <h2 className="text-2xl md:text-3xl font-extrabold text-stone-100 mt-1">{title}</h2>
    </div>
  );
}

function Chain({ items }: { items: string[] }) {
  return (
    <div className="flex flex-col items-stretch gap-1 font-mono text-xs">
      {items.map((s, i) => (
        <div key={s}>
          <div className="rounded-lg border border-stone-700/60 bg-earth-800/80 px-3 py-2 text-center text-sand">
            {s}
          </div>
          {i < items.length - 1 && <div className="text-center text-moss leading-4">↓</div>}
        </div>
      ))}
    </div>
  );
}

const EXPLORE = [
  { name: "FIELD", desc: "Multi-well site overview with live per-well thermal state.", tag: null as string | null },
  { name: "WELL", desc: "Wellhead, SRP unit and operating state for the selected well.", tag: null },
  { name: "WELLBORE", desc: "Casing, tubing and rod string in cutaway and X-ray modes.", tag: null },
  { name: "RESERVOIR", desc: "Layered oil zone with twin-driven thermal visualization.", tag: null },
  { name: "SRP", desc: "Beam-unit motion follows backend SPM; freezes at SPM 0.", tag: null },
  { name: "PUMP", desc: "Downhole pump focus with capacity and risk context.", tag: null },
  { name: "PUMP DISSECTION", desc: "Component-level cross-section inspector.", tag: "COMING SOON" },
];

const CAPABILITIES = [
  "Deterministic physics twin (thermal → viscosity → inflow → pump)",
  "CSS + SRP coupling with limiting-factor diagnosis",
  "Side-effect-free what-if simulation with deltas",
  "Joint 243-scenario grid optimization with reasons",
  "Deterministic mechanical risk indicators",
  "Interactive 3D well visualization (field → pump)",
  "Backend-connected telemetry + engineering inspector",
  "SHA-256 audit trail of ingested telemetry",
];

const STACK = ["Next.js", "React", "TypeScript", "React Three Fiber", "Three.js", "FastAPI", "Python", "Pytest", "Docker"];

const ROADMAP = [
  ["PHASE 1 · Interactive 3D Digital Twin", "CURRENT", "Field-to-pump exploration you can open today."],
  ["PHASE 2 · Historical / Public Data Platform", "FUTURE", "Time-series storage and public data ingestion."],
  ["PHASE 3 · ML Intelligence", "FUTURE", "Trained forecasting and anomaly models."],
  ["PHASE 4 · Physics + ML Hybrid Twin", "FUTURE", "Calibrated hybrid predictions."],
  ["PHASE 5 · Advanced SRP / Pump Visualization", "FUTURE", "Pump dissection and cross-sections."],
  ["PHASE 6 · CSS Intelligence", "FUTURE", "Cycle design assistance from data."],
  ["PHASE 7 · Advanced Optimization", "FUTURE", "Constrained multi-objective search."],
  ["PHASE 8 · Full Control Room", "FUTURE", "Operations-grade multi-well experience."],
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#070b14] text-slate-200 font-sans">
      {/* Nav */}
      <header className="sticky top-0 z-20 backdrop-blur bg-[#070b14]/85 border-b border-stone-700/40">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
          <Logo size={34} />
          <span className="font-extrabold tracking-wide">
            <span className="text-sand">PETRO</span><span className="text-leaf">FORGE</span>
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-clay/15 text-sand border border-clay/40">SIH26120</span>
          <div className="flex-1" />
          <Link href="#architecture" className="hidden md:inline text-xs font-mono text-slate-400 hover:text-sand">ARCHITECTURE</Link>
          <Link href="#roadmap" className="hidden md:inline text-xs font-mono text-slate-400 hover:text-sand ml-4">ROADMAP</Link>
          <Link href="/twin" className="ml-4 text-xs font-bold px-4 py-2 rounded-lg bg-gradient-to-r from-forest-700 to-leaf text-white">
            EXPLORE DIGITAL TWIN
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 pt-12 pb-10 grid md:grid-cols-2 gap-8 items-center">
        <div>
          <div className="flex flex-wrap gap-2 text-[10px] font-mono">
            <span className="px-2 py-1 rounded bg-clay/15 text-sand border border-clay/40">SIH26120</span>
            <span className="px-2 py-1 rounded bg-stone-700/60 text-stone-300 border border-stone-600/50">Oil India Limited</span>
            <span className="px-2 py-1 rounded bg-forest-800 text-leaf border border-leaf/30">Baghewala Heavy Oil</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-black mt-4 leading-tight">
            <span className="text-sand">PETRO</span><span className="text-leaf">FORGE</span>
          </h1>
          <p className="text-lg text-stone-200 mt-2 font-semibold">
            Physics + AI Digital Twin for Well-to-Surface Optimization
          </p>
          <p className="text-sm text-slate-400 mt-3 max-w-md">
            An interactive engineering platform for understanding and optimizing CSS and
            SRP operations in heavy-oil wells — reservoir to surface, twin to decision.
          </p>
          <div className="flex flex-wrap gap-3 mt-6">
            <Link href="/twin" className="text-sm font-bold px-6 py-3 rounded-xl bg-gradient-to-r from-forest-700 to-leaf text-white">
              EXPLORE DIGITAL TWIN
            </Link>
            <Link href="#architecture" className="text-sm font-mono px-6 py-3 rounded-xl border border-stone-600 text-sand hover:border-leaf/60">
              VIEW ARCHITECTURE
            </Link>
          </div>
          <p className="text-[11px] font-mono text-slate-500 mt-4">
            Prototype baseline: deterministic physics + simulation + optimization.
            ML phases are roadmap, not claims.
          </p>
        </div>
        <div className="h-[320px] md:h-[420px] rounded-2xl overflow-hidden border border-stone-700/50 bg-[#0a0f1a]">
          <HeroScene />
        </div>
      </section>

      {/* Problem */}
      <section className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="THE PROBLEM" title="Two systems, tuned in isolation" />
        <div className="grid md:grid-cols-3 gap-6">
          <div className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5">
            <h3 className="font-bold text-sand mb-3">CSS → Inflow</h3>
            <Chain items={["CSS", "Steam", "Temperature", "Viscosity", "Mobility", "Reservoir Inflow"]} />
          </div>
          <div className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5">
            <h3 className="font-bold text-sand mb-3">SRP → Lift</h3>
            <Chain items={["SRP", "Stroke + SPM", "Pump Capacity", "Lift"]} />
          </div>
          <div className="rounded-2xl border border-leaf/30 bg-forest-900/60 p-5">
            <h3 className="font-bold text-leaf mb-3">Coupled outcome</h3>
            <Chain items={["Reservoir Inflow ↔ Pump Capacity", "Production / Risk / Energy"]} />
            <p className="text-xs text-slate-400 mt-3">
              Mismatch between inflow and lift is where SOR, energy waste, and mechanical
              risk hide. PetroForge makes it visible.
            </p>
          </div>
        </div>
      </section>

      {/* Twin architecture */}
      <section id="architecture" className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="DIGITAL TWIN" title="One workflow, reservoir to decision" />
        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5">
            <h3 className="font-bold text-sand mb-3">Well-to-surface layers</h3>
            <Chain items={["Reservoir", "Wellbore", "SRP", "Surface", "Production"]} />
          </div>
          <div className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5">
            <h3 className="font-bold text-sand mb-3">Decision-support layers</h3>
            <Chain items={["Physics", "Simulation", "Risk", "Optimization", "Decision Support"]} />
          </div>
        </div>
      </section>

      {/* Explore */}
      <section className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="EXPLORE" title="What you can open in the twin" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {EXPLORE.map((c) => (
            <Link
              key={c.name}
              href="/twin"
              className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5 hover:border-leaf/50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-sand">{c.name}</h3>
                {c.tag && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-stone-700/70 text-stone-300">
                    {c.tag}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-2">{c.desc}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* Capabilities */}
      <section className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="BASELINE" title="Current capabilities — implemented today" />
        <div className="grid sm:grid-cols-2 gap-3">
          {CAPABILITIES.map((c) => (
            <div key={c} className="flex gap-2 items-start rounded-xl border border-leaf/20 bg-forest-900/40 px-4 py-3 text-sm text-stone-200">
              <span className="text-leaf font-bold">✓</span>{c}
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline */}
      <section className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="PIPELINE" title="From data to decision" />
        <div className="rounded-2xl border border-stone-700/50 bg-earth-900/60 p-5 font-mono text-xs md:text-sm">
          <div className="flex flex-wrap items-center justify-center gap-2 text-center">
            {["DATA", "PHYSICS", "TWIN", "SIMULATION", "RISK", "OPTIMIZATION", "DECISION SUPPORT"].map((s, i, a) => (
              <span key={s} className="flex items-center gap-2">
                <span className="px-3 py-2 rounded-lg bg-forest-800 text-leaf border border-leaf/25">{s}</span>
                {i < a.length - 1 && <span className="text-moss">→</span>}
              </span>
            ))}
          </div>
          <p className="text-center text-slate-500 mt-4 font-sans text-xs">
            Deterministic prototype pipeline — every value traceable to backend computation.
          </p>
        </div>
      </section>

      {/* Roadmap */}
      <section id="roadmap" className="max-w-6xl mx-auto px-4 py-10">
        <SectionTitle kicker="ROADMAP" title="Where PetroForge goes next" />
        <div className="grid md:grid-cols-2 gap-3">
          {ROADMAP.map(([t, tag, d]) => (
            <div key={t} className="rounded-xl border border-stone-700/50 bg-earth-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-bold text-stone-200">{t}</span>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  tag === "CURRENT"
                    ? "bg-leaf/15 text-leaf border border-leaf/40"
                    : "bg-stone-700/70 text-stone-400 border border-stone-600/50"
                }`}>{tag}</span>
              </div>
              <p className="text-xs text-slate-400 mt-1">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Stack + SIH */}
      <section className="max-w-6xl mx-auto px-4 py-10 grid md:grid-cols-2 gap-6">
        <div>
          <SectionTitle kicker="STACK" title="Built with" />
          <div className="flex flex-wrap gap-2">
            {STACK.map((s) => (
              <span key={s} className="text-xs font-mono px-3 py-1.5 rounded-lg bg-stone-800/70 border border-stone-600/50 text-stone-200">{s}</span>
            ))}
          </div>
        </div>
        <div>
          <SectionTitle kicker="SIH 2026" title="Submission" />
          <div className="rounded-2xl border border-clay/30 bg-earth-900/60 p-5 text-sm space-y-1">
            <div><span className="text-slate-400 font-mono text-xs">EVENT </span><strong>Smart India Hackathon 2026</strong></div>
            <div><span className="text-slate-400 font-mono text-xs">PROBLEM </span><strong>SIH26120</strong></div>
            <div><span className="text-slate-400 font-mono text-xs">ORG </span><strong>Oil India Limited</strong></div>
            <div><span className="text-slate-400 font-mono text-xs">CATEGORY </span><strong>Software</strong></div>
          </div>
        </div>
      </section>

      <footer className="border-t border-stone-700/40 mt-6">
        <div className="max-w-6xl mx-auto px-4 py-6 flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <Logo size={26} />
            <span className="font-extrabold"><span className="text-sand">PETRO</span><span className="text-leaf">FORGE</span></span>
            <span className="text-slate-500 font-mono">· Physics + AI Digital Twin · SIH26120</span>
          </div>
          <div className="flex-1" />
          <Link href="/twin" className="font-mono text-slate-400 hover:text-sand">Digital Twin</Link>
          <a href="https://github.com/sambhav-coder/Petro_Forge" className="font-mono text-slate-400 hover:text-sand">GitHub</a>
          <Link href="/twin" className="font-mono text-slate-400 hover:text-sand">Documentation</Link>
        </div>
      </footer>
    </div>
  );
}
