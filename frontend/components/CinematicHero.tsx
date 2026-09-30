"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import Logo from "@/components/Logo";

/* Local, preloaded hero imagery — generic editorial labels only.
   None depicts Baghewala Field. See public/landing/reservoirs/SOURCES.md. */
const HERO_IMAGES = [
  { src: "/landing/reservoirs/reservoir-01.jpg", label: "HEAVY OIL ENVIRONMENT" },
  { src: "/landing/reservoirs/reservoir-02.jpg", label: "STEAM-ASSISTED RECOVERY" },
  { src: "/landing/reservoirs/reservoir-03.jpg", label: "OIL PRODUCTION" },
  { src: "/landing/reservoirs/reservoir-04.jpg", label: "PUMPING OPERATIONS" },
  { src: "/landing/reservoirs/reservoir-05.jpg", label: "RESERVOIR SYSTEM" },
];

const TRANSITION_MS = 2600;

const TICKER = [
  "PHYSICS × AI × DIGITAL TWIN × WELL-TO-SURFACE OPTIMIZATION",
  "CYCLIC STEAM STIMULATION",
  "SUCKER ROD PUMP INTELLIGENCE",
  "THERMAL → VISCOSITY → INFLOW → PRODUCTION",
  "DETERMINISTIC · PROVENANCE-LABELED · ENGINEERED",
];

export default function CinematicHero() {
  const [active, setActive] = useState(0);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  /* Preload the full set so crossfades never flash. */
  useEffect(() => {
    HERO_IMAGES.forEach(({ src }) => {
      const img = new window.Image();
      img.src = src;
    });
  }, []);

  useEffect(() => {
    if (reduced) return;
    const id = setInterval(
      () => setActive((p) => (p + 1) % HERO_IMAGES.length),
      TRANSITION_MS
    );
    return () => clearInterval(id);
  }, [reduced]);

  return (
    <section
      className="relative min-h-screen w-full flex flex-col items-center justify-center overflow-hidden"
      aria-label="PetroForge cinematic introduction"
    >
      {/* Image stack — soft crossfade + slow ken-burns drift */}
      <div aria-hidden="true" className="absolute inset-0 z-0">
        {HERO_IMAGES.map(({ src }, i) => (
          <div
            key={src}
            className="absolute inset-0 will-change-[opacity,transform]"
            style={{
              opacity: active === i ? 1 : 0,
              transform: active === i ? "scale(1.02)" : "scale(1.1)",
              transition: reduced
                ? "none"
                : "opacity 2s cubic-bezier(0.22,1,0.36,1), transform 8s ease-out",
            }}
          >
            <Image
              src={src}
              alt=""
              fill
              priority={i === 0}
              sizes="100vw"
              style={{ objectFit: "cover", objectPosition: "center 62%" }}
            />
          </div>
        ))}
        {/* Legibility layers — image stays recognisable */}
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,16,13,0.62) 0%, rgba(7,16,13,0.38) 34%, rgba(7,16,13,0.55) 66%, #07100D 100%)",
          }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(115deg, rgba(18,63,42,0.42) 0%, transparent 46%, rgba(90,58,36,0.30) 100%)",
          }}
        />
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-28"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,16,13,0.75) 0%, transparent 100%)",
          }}
        />
      </div>

      {/* Current frame caption */}
      <div
        aria-hidden="true"
        className="absolute z-[5] bottom-24 right-6 md:right-10 text-[9.5px] font-mono tracking-[0.3em] text-cream-soft/45"
      >
        {HERO_IMAGES[active].label} · {String(active + 1).padStart(2, "0")}/0{HERO_IMAGES.length}
      </div>

      {/* Hero content */}
      <div className="relative z-10 w-full max-w-6xl mx-auto px-6 pt-24 pb-28 flex flex-col items-center text-center">
        <div className="animate-fadeUp" style={{ transitionDelay: "0.1s" }}>
          <Logo size={88} animated />
        </div>

        <h1 className="mt-9 animate-fadeUp" style={{ transitionDelay: "0.25s" }}>
          <span
            className="gradient-text font-display font-black tracking-[0.08em] leading-[1.05] text-[clamp(2.8rem,8vw,6.4rem)]"
            style={{ filter: "drop-shadow(0 2px 26px rgba(7,16,13,0.85))" }}
          >
            PETROFORGE
          </span>
        </h1>

        <p
          className="mt-5 animate-fadeUp text-[clamp(0.88rem,1.8vw,1.08rem)] font-medium text-cream-soft/85 tracking-[0.02em] max-w-xl leading-relaxed"
          style={{ transitionDelay: "0.42s", textShadow: "0 1px 18px rgba(7,16,13,0.9)" }}
        >
          AI + physics well-to-surface digital twin for heavy-oil CSS &amp; SRP
          operations — reservoir to production, one coupled model.
        </p>

        <div className="hairline w-56 mt-9 animate-fadeUp" style={{ transitionDelay: "0.55s" }} />

        {/* THE single primary CTA */}
        <div className="mt-9 animate-fadeUp" style={{ transitionDelay: "0.68s" }}>
          <Link
            href="/twin"
            className="cta-primary inline-flex items-center gap-3 group
              px-10 py-4 rounded-xl
              text-[12.5px] font-semibold font-mono tracking-[0.22em] uppercase text-cream-soft
              bg-gradient-to-r from-forest-deep via-petroleum to-crude/70
              border border-natural/40
              shadow-glow
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-natural"
            aria-label="Enter the PetroForge Digital Twin"
          >
            <span>DIGITAL TWIN</span>
            <svg width="18" height="14" viewBox="0 0 18 14"
              className="transition-transform duration-300 group-hover:translate-x-1.5" aria-hidden="true">
              <line x1="0" y1="7" x2="15" y2="7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.75" />
              <polyline points="11,3 17,7 11,11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </div>

        <div
          className="mt-16 flex flex-wrap items-center justify-center gap-x-6 gap-y-3
            text-[10.5px] font-mono text-cream-soft/60 tracking-[0.16em] uppercase animate-fadeUp"
          style={{ transitionDelay: "0.9s", textShadow: "0 1px 12px rgba(7,16,13,0.9)" }}
        >
          <span className="flex items-center gap-2">
            <span className="status-dot pulse text-natural" style={{ background: "currentColor" }} />
            Deterministic Physics
          </span>
          <span className="opacity-40">·</span>
          <span>Reservoir → Surface</span>
          <span className="opacity-40">·</span>
          <span>CSS × SRP Coupled</span>
        </div>
      </div>

      {/* Industrial data ticker */}
      <div
        className="relative z-10 w-full overflow-hidden py-4 border-y border-cream-soft/10"
        style={{ background: "rgba(7,16,13,0.55)", backdropFilter: "blur(6px)" }}
      >
        <div className="marquee-track gap-0 px-0" aria-hidden="true">
          {[...TICKER, ...TICKER].map((item, i) => (
            <span key={i} className="text-[11px] font-mono font-semibold tracking-[0.24em] uppercase text-cream-soft/70 whitespace-nowrap">
              <span className="text-natural/70 mx-8">◆</span>
              {item}
            </span>
          ))}
        </div>
        <span className="sr-only">{TICKER.join(". ")}</span>
      </div>
    </section>
  );
}
