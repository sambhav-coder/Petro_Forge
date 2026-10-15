"use client";

import { api } from "./api";
import type { CopilotFinding, CopilotSession, CopilotSimulateResponse, CopilotState } from "./types";

/* Co-Pilot session state machine: deterministic, testable transitions. */
const TRANSITIONS: Record<CopilotState, CopilotState[]> = {
  IDLE: ["INITIALIZING"],
  INITIALIZING: ["COLLECTING_EVIDENCE", "ERROR", "CANCELLED"],
  COLLECTING_EVIDENCE: ["ANALYZING", "INSUFFICIENT_DATA", "PARTIAL_RESULTS", "ERROR", "CANCELLED"],
  ANALYZING: ["SIMULATING", "NARRATING", "PARTIAL_RESULTS", "ERROR", "CANCELLED"],
  SIMULATING: ["NARRATING", "PARTIAL_RESULTS", "ERROR", "CANCELLED"],
  NARRATING: ["COMPLETED", "PAUSED", "ERROR", "CANCELLED"],
  PAUSED: ["NARRATING", "CANCELLED", "COMPLETED"],
  COMPLETED: ["IDLE"],
  INSUFFICIENT_DATA: ["IDLE"],
  PARTIAL_RESULTS: ["NARRATING", "COMPLETED", "IDLE"],
  ERROR: ["IDLE"],
  CANCELLED: ["IDLE"],
};

export function canTransition(from: CopilotState, to: CopilotState): boolean {
  return (TRANSITIONS[from] ?? []).includes(to);
}

export interface CopilotRun {
  session: CopilotSession | null;
  findings: CopilotFinding[];
  simulation: CopilotSimulateResponse | null;
  autoSimulated: boolean;
}

/* Budgets: ≤3 auto sims, bounded wall-clock, bounded parallelism. */
export const COPILOT_BUDGETS = { maxAutoSims: 3, sessionTimeoutMs: 120_000, maxParallel: 4 };

/** Orchestrate a Live Co-Pilot run. Stale-session safe via runToken. */
export async function runCopilotSession(
  wellId: string,
  runToken: { current: number },
  onStage: (s: CopilotState, note?: string) => void,
  signal?: AbortSignal
): Promise<CopilotRun> {
  const myRun = ++runToken.current;
  const alive = () => runToken.current === myRun && !signal?.aborted;
  const check = () => {
    if (!alive()) throw new Error("__CANCELLED__");
  };

  onStage("INITIALIZING");
  const session = await api.copilotSession(wellId);
  check();
  if (!alive()) throw new Error("__CANCELLED__");

  onStage("COLLECTING_EVIDENCE");
  // Session already aggregates evidence server-side; analyze adds narration.
  const stages = session.stages.slice(0, 6);
  onStage("ANALYZING");
  let findings = session.findings;
  try {
    const az = await api.copilotAnalyze(wellId, stages);
    check();
    if (az.findings.length > 0) findings = az.findings;
  } catch {
    onStage("PARTIAL_RESULTS", "analysis partial; baseline evidence retained");
  }

  if (!session.has_telemetry) {
    onStage("INSUFFICIENT_DATA", "no telemetry; simulation skipped");
    return { session, findings, simulation: null, autoSimulated: false };
  }

  // Bounded autonomous simulation: one conservative SPM+1 scenario.
  onStage("SIMULATING");
  let simulation: CopilotSimulateResponse | null = null;
  let autoSimulated = false;
  try {
    const tele = await api.well(wellId).catch(() => null);
    check();
    const spm = tele && typeof (tele as { spm?: number }).spm === "number"
      ? Math.min(8, Math.max(1, (tele as { spm: number }).spm + 1))
      : 6;
    simulation = await api.copilotSimulate(wellId, [{ spm }]);
    check();
    autoSimulated = true;
  } catch (e) {
    if ((e as Error).message === "__CANCELLED__") throw e;
    onStage("PARTIAL_RESULTS", "simulation unavailable; findings retained");
  }

  onStage("NARRATING");
  return { session, findings, simulation, autoSimulated };
}

export function findingSeverityTone(sev: string): string {
  const s = sev.toUpperCase();
  if (s === "HIGH") return "text-rose-300 border-rose-500/30 bg-rose-500/10";
  if (s === "MODERATE") return "text-amber-warm border-amber-warm/30 bg-amber-warm/10";
  if (s === "INFO") return "text-natural border-natural/30 bg-natural/10";
  return "text-sand/70 border-natural/15 bg-oil-black/40";
}

/* ---- 2.0: full presentation plan runner ---- */

export interface PlanSegment {
  segment_id: string;
  well_id: string;
  sequence: number;
  stage: string;
  title: string;
  narration_text: string;
  spoken_text: string;
  speech_chunks: string[];
  evidence_refs: string[];
  data_provenance: string;
  component_focus: string;
  camera_action: string;
  related_values: Array<{ name: string; value: number | string | null; provenance?: string }>;
  animation_action: string;
  simulation_id: string | null;
  duration_hint_s: number;
  completion_condition: string;
  available: boolean;
  unavailable_reason: string;
}

export interface PresentationPlan {
  well_id: string;
  segments: PlanSegment[];
  coverage: {
    total: number;
    available: number;
    skipped: Array<{ segment_id: string; title: string; reason: string }>;
  };
  simulation_only: boolean;
}

export type SegmentEvent =
  | { type: "segment-start"; segment: PlanSegment; index: number; total: number }
  | { type: "segment-end"; segment: PlanSegment; index: number }
  | { type: "complete"; completed: number; skipped: number };

/**
 * Execute the full presentation: for each available segment, apply camera
 * focus, speak its text, and advance ONLY on audio completion (or text dwell
 * when voice is off). Skipped chapters are reported, never silently dropped.
 * Pause/resume/skip/stop driven by the controller callbacks from the panel.
 */
export interface PresentationController {
  waitTurn: (segment: PlanSegment, index: number) => Promise<"next" | "replay" | "stop">;
  speakAndWait: (segment: PlanSegment) => Promise<void>;
  onEvent: (e: SegmentEvent) => void;
  isAlive: () => boolean;
}

export async function runPresentation(
  plan: PresentationPlan,
  ctl: PresentationController
): Promise<{ completed: number; skipped: number }> {
  let completed = 0;
  const skipped = plan.coverage.skipped.length;
  const total = plan.segments.length;
  for (let i = 0; i < plan.segments.length; i += 1) {
    if (!ctl.isAlive()) throw new Error("__CANCELLED__");
    const seg = plan.segments[i];
    if (!seg.available) continue; // counted in coverage.skipped
    ctl.onEvent({ type: "segment-start", segment: seg, index: i, total });
    // eslint-disable-next-line no-await-in-loop
    await ctl.speakAndWait(seg);
    if (!ctl.isAlive()) throw new Error("__CANCELLED__");
    ctl.onEvent({ type: "segment-end", segment: seg, index: i });
    completed += 1;
    // eslint-disable-next-line no-await-in-loop
    const turn = await ctl.waitTurn(seg, i);
    if (turn === "stop") throw new Error("__CANCELLED__");
    if (turn === "replay") {
      if (!ctl.isAlive()) throw new Error("__CANCELLED__");
      ctl.onEvent({ type: "segment-start", segment: seg, index: i, total });
      // eslint-disable-next-line no-await-in-loop
      await ctl.speakAndWait(seg);
      ctl.onEvent({ type: "segment-end", segment: seg, index: i });
    }
  }
  ctl.onEvent({ type: "complete", completed, skipped });
  return { completed, skipped };
}
