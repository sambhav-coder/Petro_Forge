"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  COPILOT_BUDGETS, canTransition, findingSeverityTone, runCopilotSession,
  runPresentation, type PlanSegment, type PresentationPlan,
} from "@/lib/copilot";
import type { CopilotFinding, CopilotSimulateResponse, CopilotSession, CopilotState } from "@/lib/types";
import {
  listenOnce, pauseSpeak, resumeSpeak, speakQueue, stopQueue,
  sttSupported, ttsSupported, warmVoices,
} from "@/lib/voice";
import { fmt } from "@/lib/scene";

const STAGE_LABEL: Record<string, string> = {
  welcome: "Welcome", model: "3D Model", telemetry: "Telemetry", hybrid: "Hybrid Twin",
  srp: "SRP", css: "CSS Cycle", alerts: "Alerts", simulation: "Simulation",
  optimization: "Optimization", summary: "Summary",
};

export default function CopilotPanel({
  wellId,
  autoStartKey,
  onHighlight,
  onSpeakState,
  onStage,
  onRequestPanel,
}: {
  wellId: string | null;
  autoStartKey: number;
  onHighlight: (kind: string) => void;
  onSpeakState: (mode: "idle" | "listening" | "explaining" | "speaking") => void;
  onStage: (s: CopilotState) => void;
  onRequestPanel: (tab: string) => void;
}) {
  const [state, setState] = useState<CopilotState>("IDLE");
  const [note, setNote] = useState<string | null>(null);
  const [session, setSession] = useState<CopilotSession | null>(null);
  const [findings, setFindings] = useState<CopilotFinding[]>([]);
  const [sim, setSim] = useState<CopilotSimulateResponse | null>(null);
  const [plan, setPlan] = useState<PresentationPlan | null>(null);
  const [segIdx, setSegIdx] = useState(-1);
  const [segState, setSegState] = useState<Record<string, "done" | "skipped" | "failed">>({});
  const [transcript, setTranscript] = useState<{ stage: string; text: string }[]>([]);
  const [subtitles, setSubtitles] = useState(true);
  const [narrationOn, setNarrationOn] = useState(true);
  const [auto, setAuto] = useState(true);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [listening, setListening] = useState(false);
  const [report, setReport] = useState<{ completed: number; skipped: number } | null>(null);
  const runToken = useRef(0);
  const pauseRef = useRef(false);
  const skipRef = useRef(false);
  const replayRef = useRef(false);
  const turnResolve = useRef<((v: "next" | "replay" | "stop") => void) | null>(null);
  const reduceMotion = useMemo(
    () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
    []
  );

  const setStage = useCallback((next: CopilotState, n?: string) => {
    setState((prev) => {
      if (prev === next) { if (n) setNote(n); return prev; }
      if (!canTransition(prev, next) && !(prev === "PAUSED" && next === "PAUSED")) {
        if (!["IDLE", "ERROR", "CANCELLED"].includes(next)) return prev;
      }
      if (n !== undefined) setNote(n);
      onStage(next);
      return next;
    });
  }, [onStage]);

  const pushTranscript = useCallback((stage: string, text: string) => {
    setTranscript((t) => [...t.slice(-49), { stage, text }]);
  }, []);

  const focusFor = useCallback((seg: PlanSegment) => {
    // One authoritative segment drives camera + panel + narration together.
    onHighlight(seg.component_focus);
    onRequestPanel(seg.panel_tab);
    try {
      document.getElementById("copilot-right-panel")?.scrollTo({ top: 0, behavior: "smooth" });
    } catch { /* scroll is best-effort */ }
  }, [onHighlight, onRequestPanel]);

  /* Speak one segment; resolve ONLY on audio completion (or timed dwell in text mode). */
  const speakAndWait = useCallback((seg: PlanSegment): Promise<void> => {
    focusFor(seg);
    pushTranscript(seg.stage, seg.narration_text);
    if (!narrationOn || !ttsSupported()) {
      onSpeakState("explaining");
      const dwell = reduceMotion ? 600 : Math.min(9000, 2500 + seg.spoken_text.length * 12);
      return new Promise((res) => setTimeout(res, auto ? dwell : 1200));
    }
    onSpeakState("speaking");
    return new Promise((res) => {
      const ok = speakQueue(seg.spoken_text, {
        lang: "hi-IN",
        onDone: () => { onSpeakState("explaining"); res(); },
      });
      if (!ok) { onSpeakState("explaining"); res(); }
    });
  }, [focusFor, pushTranscript, narrationOn, auto, reduceMotion, onSpeakState]);

  const start = useCallback(async () => {
    if (!wellId) return;
    warmVoices();
    stopQueue();
    runToken.current += 1;
    const myRun = runToken.current;
    const alive = () => runToken.current === myRun;
    pauseRef.current = false; skipRef.current = false; replayRef.current = false;
    setSession(null); setFindings([]); setSim(null); setPlan(null);
    setSegState({}); setAnswer(null); setTranscript([]); setSegIdx(-1); setReport(null);
    try {
      setStage("INITIALIZING");
      const [run, fullPlan] = await Promise.all([
        runCopilotSession(wellId, { current: 0 }, () => undefined),
        api.copilotPlan(wellId),
      ]);
      if (!alive()) return;
      setSession(run.session);
      setFindings(run.findings);
      setSim(run.simulation);
      setPlan(fullPlan);
      setStage("NARRATING");
      const ctl = {
        isAlive: alive,
        onEvent: (e: { type: string; segment?: PlanSegment; index?: number; completed?: number; skipped?: number }) => {
          if (!alive()) return;
          if (e.type === "segment-start" && e.segment) {
            setSegIdx(e.index ?? -1);
          } else if (e.type === "segment-end" && e.segment) {
            setSegState((s) => ({ ...s, [e.segment!.segment_id]: "done" }));
          } else if (e.type === "complete") {
            setReport({ completed: e.completed ?? 0, skipped: e.skipped ?? 0 });
          }
        },
        speakAndWait,
        waitTurn: (seg: PlanSegment) => new Promise<"next" | "replay" | "stop">((res) => {
          if (skipRef.current) { skipRef.current = false; res("next"); return; }
          if (!auto) {
            // Manual mode: wait for explicit Next/Skip/Replay press.
            turnResolve.current = res;
            return;
          }
          const dwell = 700;
          setTimeout(() => res("next"), dwell);
        }),
      };
      await runPresentation(fullPlan, ctl);
      if (!alive()) return;
      setStage("COMPLETED");
      onSpeakState("idle");
    } catch (e) {
      if ((e as Error).message === "__CANCELLED__") setStage("CANCELLED");
      else setStage("ERROR", e instanceof Error ? e.message : "Co-Pilot failed");
      onSpeakState("idle");
    }
  }, [wellId, auto, setStage, onSpeakState, speakAndWait]);

  useEffect(() => {
    if (autoStartKey > 0 && wellId) start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStartKey]);

  const stop = useCallback(() => {
    runToken.current += 1;
    stopQueue();
    turnResolve.current?.("stop");
    turnResolve.current = null;
    setStage("CANCELLED", "presentation stopped by user");
    onSpeakState("idle");
  }, [setStage, onSpeakState]);

  const pause = useCallback(() => {
    pauseRef.current = true;
    pauseSpeak();
    setStage("PAUSED", "narration paused — Resume to continue from this chapter");
    onSpeakState("idle");
  }, [setStage, onSpeakState]);

  const resume = useCallback(() => {
    pauseRef.current = false;
    if (!resumeSpeak()) { /* chunk queue restarts current chunk on next segment */ }
    setStage("NARRATING");
    turnResolve.current?.("next");
    turnResolve.current = null;
  }, [setStage]);

  const nextSeg = useCallback(() => {
    turnResolve.current?.("next");
    turnResolve.current = null;
    if (auto) { skipRef.current = true; stopQueue(); }
  }, [auto]);

  const replaySeg = useCallback(() => {
    if (auto) { replayRef.current = true; }
    turnResolve.current?.("replay");
    turnResolve.current = null;
  }, [auto]);

  const ask = useCallback(async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || !wellId || asking) return;
    setAsking(true);
    try {
      const r = await api.copilotAsk(wellId, text, session?.session_id);
      setAnswer(`[${r.mode}] ${r.answer}`);
      pushTranscript("follow-up", r.answer);
      if (narrationOn && ttsSupported()) {
        onSpeakState("speaking");
        speakQueue(r.answer, { lang: "hi-IN", onDone: () => onSpeakState("idle") });
      }
    } catch (e) {
      setAnswer(`Error: ${e instanceof Error ? e.message : "ask failed"}`);
    } finally {
      setAsking(false);
    }
  }, [question, wellId, asking, session, narrationOn, onSpeakState, pushTranscript]);

  const voiceAsk = useCallback(async () => {
    if (listening) return;
    setListening(true);
    onSpeakState("listening");
    const text = await listenOnce({ lang: "hi-IN" });
    setListening(false);
    onSpeakState("idle");
    if (text) { setQuestion(text); ask(text); }
  }, [listening, onSpeakState, ask]);

  if (!wellId) {
    return (
      <div className="rounded-xl border border-natural/15 bg-oil-black/50 p-4 text-[12px] text-sand/60">
        Select a well, then press <span className="font-bold text-cream-soft">▶ LIVE</span> for the full guided presentation.
      </div>
    );
  }

  const simRow = sim?.simulations[0];
  const current = plan?.segments[segIdx];
  return (
    <section aria-label="PetroForge AI Co-Pilot presentation" className="space-y-3">
      {/* Header */}
      <div className="rounded-xl border border-natural/20 bg-oil-black/60 p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm" aria-hidden="true">👷</span>
          <div className="font-display font-bold tracking-[0.1em] text-[12px] text-cream-soft">AI CO-PILOT · FULL PRESENTATION</div>
          <span className="ml-auto font-mono text-[10px] px-2 py-0.5 rounded border border-natural/20 text-sand/70" aria-live="polite">
            {state}
          </span>
        </div>
        <div className="mt-1 text-[11px] font-mono text-sand/55">
          Well <span className="text-natural">{wellId}</span>
          {session && <span> · <span className="text-sand/80">{session.session_id}</span></span>}
          {session && <span> · <span className="text-amber-warm">{session.mode === "LLM" ? "LLM" : "TEMPLATE (not LLM)"}</span></span>}
          {plan && <span> · chapters {plan.coverage.available}/{plan.coverage.total}</span>}
        </div>
        {current && (
          <div className="mt-1 text-[11.5px] text-cream-soft/90" aria-live="polite">
            <span className="font-mono text-natural">Ch.{current.sequence} {STAGE_LABEL[current.stage] ?? current.stage}:</span> {current.title}
          </div>
        )}
        {note && <div className="mt-1 text-[11px] text-amber-warm/90">{note}</div>}
        {state === "ERROR" && (
          <div className="mt-1 text-[11px] text-rose-300">Co-Pilot hit an error — Detail Panel controls still work. Press Start to retry.</div>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Presentation controls">
          <button onClick={start} className="copilot-btn" aria-label="Start full presentation">▶ Present</button>
          <button onClick={pause} className="copilot-btn" aria-label="Pause">⏸ Pause</button>
          <button onClick={resume} className="copilot-btn" aria-label="Resume">↻ Resume</button>
          <button onClick={nextSeg} className="copilot-btn" aria-label="Skip to next chapter">⏭ Skip</button>
          <button onClick={replaySeg} className="copilot-btn" aria-label="Replay chapter">⟲ Replay</button>
          <button onClick={stop} className="copilot-btn" aria-label="Stop">⏹ Stop</button>
          <button onClick={() => setAuto((a) => !a)} className="copilot-btn" aria-pressed={auto}>{auto ? "Auto ✓" : "Manual"}</button>
          <button onClick={() => onHighlight("overview")} className="copilot-btn" aria-label="Reset 3D view to overview">▦ Overview</button>
          <button onClick={() => setNarrationOn((v) => !v)} className="copilot-btn" aria-pressed={narrationOn}>
            {narrationOn ? "🔊 Voice on" : "🔇 Text only"}
          </button>
          <button onClick={() => setSubtitles((v) => !v)} className="copilot-btn" aria-pressed={subtitles}>
            {subtitles ? "Subtitles ✓" : "Subtitles off"}
          </button>
        </div>
        {!ttsSupported() && (
          <div className="mt-1 text-[10px] font-mono text-sand/45">Voice unavailable — text + subtitles continue. Neural provider: not configured (honest fallback).</div>
        )}
      </div>

      {/* Chapter timeline */}
      {plan && (
        <div className="rounded-xl border border-natural/15 bg-oil-black/50 p-3">
          <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-sand/45">Chapters · auto-advanced on narration end</div>
          <ol className="mt-2 space-y-1">
            {plan.segments.map((s, i) => {
              const st = segState[s.segment_id];
              return (
                <li key={s.segment_id}
                  className={`flex items-center gap-2 rounded-lg border px-2 py-1 text-[11px] font-mono ${
                    i === segIdx ? "border-natural/50 bg-natural/10 text-cream-soft"
                    : st === "done" ? "border-natural/15 text-natural/80"
                    : !s.available ? "border-natural/10 text-sand/35"
                    : "border-natural/10 text-sand/60"}`}>
                  <span className="w-6 shrink-0">{String(s.sequence).padStart(2, "0")}</span>
                  <span className="flex-1 truncate">{STAGE_LABEL[s.stage] ?? s.stage} — {s.title}</span>
                  <span className="shrink-0">{!s.available ? `SKIP (${s.unavailable_reason.slice(0, 28)})` : st === "done" ? "✓" : i === segIdx ? "▶" : "·"}</span>
                </li>
              );
            })}
          </ol>
          {report && (
            <div className="mt-2 rounded-lg border border-natural/25 bg-natural/5 p-2 font-mono text-[10.5px] text-cream-soft/90">
              Presentation complete: {report.completed} chapters presented, {report.skipped} skipped (data unavailable).
              Simulated values were not applied to any real well.
            </div>
          )}
        </div>
      )}

      {/* Subtitles */}
      {transcript.length > 0 && subtitles && (
        <div className="rounded-xl border border-natural/15 bg-forest-deep/40 p-3" aria-live="polite">
          <div className="text-[9px] font-mono tracking-[0.2em] uppercase text-sand/40">Subtitles · Hindi/Hinglish (matches spoken audio)</div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-cream-soft">{transcript[transcript.length - 1].text}</p>
        </div>
      )}

      {/* Findings */}
      <div className="rounded-xl border border-natural/15 bg-oil-black/50 p-3">
        <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-sand/45">Findings · evidence-backed</div>
        {findings.length === 0 && <div className="mt-1 text-[11px] text-sand/50">No findings yet — press Present.</div>}
        <ul className="mt-2 space-y-2">
          {findings.map((f) => (
            <li key={f.finding_id} className={`rounded-lg border p-2 ${findingSeverityTone(f.severity)}`}>
              <div className="text-[12px] font-bold text-cream-soft">{f.title}
                <span className="ml-2 font-mono text-[9px] font-normal opacity-70">{f.severity} · {f.provenance}</span>
              </div>
              <p className="text-[11.5px] leading-snug opacity-90">{f.explanation}</p>
              {f.values.length > 0 && (
                <div className="mt-1 font-mono text-[10.5px] opacity-80">
                  {f.values.slice(0, 3).map((v, i) => (
                    <span key={i} className="mr-2">{v.name}={typeof v.value === "number" ? fmt(v.value) : String(v.value)} {v.unit ?? ""} [{v.provenance ?? f.provenance}]</span>
                  ))}
                </div>
              )}
              <div className="mt-1 text-[10px] opacity-70">Limit: {f.limitations}</div>
            </li>
          ))}
        </ul>
      </div>

      {/* Simulation comparison */}
      <div className="rounded-xl border border-amber-warm/25 bg-amber-warm/5 p-3">
        <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-amber-warm/90">
          Scenario comparison · SIMULATION-ONLY (not applied)
        </div>
        {!simRow && <div className="mt-1 text-[11px] text-sand/55">No bounded simulation yet (needs telemetry; max {COPILOT_BUDGETS.maxAutoSims}/session).</div>}
        {sim && simRow && (
          <div className="mt-2 font-mono text-[11px] text-cream-soft">
            <div>Baseline (OBSERVED): {fmt(sim.baseline.estimated_oil_production_bopd)} bopd · SOR {sim.baseline.steam_oil_ratio_t_per_bbl ?? "—"}</div>
            <div className="text-natural">Simulated ({simRow.simulation_id}): {fmt(simRow.scenario.estimated_oil_production_bopd)} bopd · Δ {fmt(simRow.delta.production_delta_bopd)} bopd</div>
            <div className="text-sand/60">Inputs: {Object.entries(simRow.inputs).map(([k, v]) => `${k}=${v}`).join(", ")}</div>
          </div>
        )}
      </div>

      {/* Q&A */}
      <div className="rounded-xl border border-natural/15 bg-oil-black/50 p-3">
        <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-sand/45">Follow-up · text + voice</div>
        <div className="mt-2 flex gap-1.5">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
            placeholder="Sawaal likhein… (e.g. SOR kyun high hai?)"
            aria-label="Ask the Co-Pilot"
            className="flex-1 min-w-0 rounded-lg border border-natural/20 bg-oil-black/60 px-2.5 py-1.5 text-[12px] text-cream-soft placeholder:text-sand/35 focus:outline-none focus:border-natural/40"
          />
          <button onClick={() => ask()} disabled={asking} className="copilot-btn" aria-label="Send question">Ask</button>
          <button onClick={voiceAsk} disabled={listening || !sttSupported()} title={sttSupported() ? "Voice question (mic after click)" : "Voice input unavailable"}
            className="copilot-btn" aria-label="Voice question">🎤</button>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {["Current condition kya hai?", "SOR aur energy tradeoff samjhao", "Agle investigation step kya hai?"].map((s) => (
            <button key={s} onClick={() => { setQuestion(s); ask(s); }} className="copilot-chip">{s}</button>
          ))}
        </div>
        {answer && <p className="mt-2 text-[12px] leading-relaxed text-cream-soft/90">{answer}</p>}
      </div>

      {/* Transcript */}
      <details className="rounded-xl border border-natural/15 bg-oil-black/40 p-3">
        <summary className="cursor-pointer text-[11px] font-mono text-sand/60">Transcript ({transcript.length}) · Evidence · Limitations</summary>
        <ol className="mt-2 space-y-1.5">
          {transcript.map((t, i) => (
            <li key={i} className="text-[11px] text-sand/75"><span className="text-natural font-mono">[{STAGE_LABEL[t.stage] ?? t.stage}]</span> {t.text}</li>
          ))}
        </ol>
        <div className="mt-2 text-[10.5px] font-mono text-sand/50">
          Simulation-only: no field control issued, no production data written. Prototype physics [PROTO], not field-validated.
          {reduceMotion ? " Reduced-motion respected." : ""}
        </div>
      </details>

      <style jsx>{`
        .copilot-btn { font-family: monospace; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
          padding: 5px 10px; border-radius: 8px; border: 1px solid rgba(45,212,191,0.25); color: #e8ddc8; background: rgba(7,11,20,0.5); }
        .copilot-btn:hover { border-color: rgba(45,212,191,0.5); }
        .copilot-btn:disabled { opacity: 0.4; }
        .copilot-chip { font-family: monospace; font-size: 10px; padding: 3px 8px; border-radius: 999px;
          border: 1px solid rgba(201,160,106,0.3); color: rgba(232,221,200,0.75); }
        .copilot-chip:hover { color: #fff; border-color: rgba(201,160,106,0.6); }
      `}</style>
    </section>
  );
}
