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
