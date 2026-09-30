"use client";

import Logo from "@/components/Logo";
import CinematicHero from "@/components/CinematicHero";
import SystemFlow from "@/components/SystemFlow";
import StoryModules from "@/components/StoryModules";

/* Landing: cinematic oil environment → PETROFORGE → ticker → DIGITAL TWIN
 * → engineering story → system visualizations → minimal identity footer.
 * One primary CTA only. */

export default function Landing() {
  return (
    <main className="min-h-screen bg-oil-black text-cream-soft font-sans overflow-x-hidden relative">
      <CinematicHero />

      {/* ============================================================
          ENGINEERING STORY — how PetroForge understands a well
          ============================================================ */}
      <section className="relative z-10 max-w-7xl mx-auto px-6 pt-24 pb-10" aria-labelledby="story-title">
        <div className="text-center mb-14">
          <div className="text-[10px] font-mono font-semibold tracking-[0.3em] uppercase text-natural/65 mb-3">
            — How PetroForge understands a well —
          </div>
          <h2 id="story-title"
            className="font-display font-semibold tracking-[0.04em] text-[clamp(1.8rem,4vw,2.8rem)] text-cream-soft leading-tight">
            Reservoir heat becomes <span className="text-natural">production</span>;
            <br className="hidden md:block" /> the pump obeys <span className="text-amber-warm">what inflow allows</span>.
          </h2>
          <p className="mt-5 max-w-2xl mx-auto text-[12.5px] leading-relaxed text-sand/60">
            One coupled chain, solved end to end. Steam raises temperature,
            temperature collapses viscosity, mobility drives inflow — and the
            SRP unit can only lift what the reservoir delivers. Every node
            below maps to a backend engine.
          </p>
        </div>

        <SystemFlow />
      </section>

      {/* ============================================================
          SYSTEM MODULES — asymmetric visual sections
          ============================================================ */}
      <section className="relative z-10 max-w-7xl mx-auto px-6 py-16" aria-labelledby="modules-title">
        <h2 id="modules-title" className="sr-only">PetroForge system modules</h2>
        <StoryModules />
      </section>

      {/* ============================================================
          MINIMAL IDENTITY FOOTER
          ============================================================ */}
      <footer className="relative z-10 border-t border-natural/8">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <Logo size={30} animated />
            <div className="leading-tight">
              <div className="text-[13px] font-display font-semibold tracking-[0.18em]">
                <span className="text-sand/85">PETRO</span>
                <span className="text-natural/85">FORGE</span>
              </div>
              <div className="text-[10px] font-mono tracking-[0.14em] text-sand/45 uppercase mt-0.5">
                Physics × AI × Digital Twin
              </div>
            </div>
          </div>
          <div className="text-[10px] font-mono text-sand/40 tracking-wide">
            SIH26120 · Prototype Platform · Deterministic values, not claims.
          </div>
        </div>
      </footer>
    </main>
  );
}
