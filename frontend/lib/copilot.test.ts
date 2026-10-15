import { describe, expect, it } from "vitest";
import {
  canTransition,
  runPresentation,
  type PlanSegment,
  type PresentationPlan,
} from "./copilot";

function seg(partial: Partial<PlanSegment> & { segment_id: string; sequence: number }): PlanSegment {
  return {
    well_id: "W-1",
    stage: "telemetry",
    title: "t",
    narration_text: "n",
    spoken_text: "s",
    speech_chunks: ["s"],
    evidence_refs: [],
    data_provenance: "OBSERVED",
    component_focus: "well",
    camera_action: "WELL",
    panel_tab: "TELEMETRY",
    panel_section: "copilot-telemetry",
    related_values: [],
    animation_action: "highlight",
    simulation_id: null,
    duration_hint_s: 8,
    completion_condition: "audio_end",
    available: true,
    unavailable_reason: "",
    ...partial,
  };
}

function planOf(segments: PlanSegment[]): PresentationPlan {
  return {
    well_id: "W-1",
    segments,
    coverage: {
      total: segments.length,
      available: segments.filter((s) => s.available).length,
      skipped: segments.filter((s) => !s.available).map((s) => ({
        segment_id: s.segment_id, title: s.title, reason: s.unavailable_reason,
      })),
    },
    simulation_only: true,
  };
}

describe("copilot state machine", () => {
  it("allows the presentation lifecycle and rejects jumps", () => {
    expect(canTransition("IDLE", "INITIALIZING")).toBe(true);
    expect(canTransition("INITIALIZING", "NARRATING")).toBe(true);
    expect(canTransition("NARRATING", "COMPLETED")).toBe(true);
    expect(canTransition("PAUSED", "NARRATING")).toBe(true);
    expect(canTransition("IDLE", "COMPLETED")).toBe(false);
    expect(canTransition("COMPLETED", "NARRATING")).toBe(false);
    expect(canTransition("NARRATING", "INITIALIZING")).toBe(false);
  });
});

describe("runPresentation", () => {
  it("presents available segments in order and skips unavailable ones", async () => {
    const plan = planOf([
      seg({ segment_id: "SEG-01", sequence: 1 }),
      seg({ segment_id: "SEG-02", sequence: 2, available: false, unavailable_reason: "no data" }),
      seg({ segment_id: "SEG-03", sequence: 3 }),
    ]);
    const events: string[] = [];
    const spoken: string[] = [];
    const res = await runPresentation(plan, {
      isAlive: () => true,
      onEvent: (e) => {
        if (e.type === "segment-start") events.push(`start:${e.segment.segment_id}`);
        if (e.type === "segment-end") events.push(`end:${e.segment.segment_id}`);
        if (e.type === "complete") events.push(`complete:${e.completed}/${e.skipped}`);
      },
      speakAndWait: async (s) => { spoken.push(s.segment_id); },
      waitTurn: async () => "next",
    });
    expect(res).toEqual({ completed: 2, skipped: 1 });
    expect(events).toEqual(["start:SEG-01", "end:SEG-01", "start:SEG-03", "end:SEG-03", "complete:2/1"]);
    expect(spoken).toEqual(["SEG-01", "SEG-03"]); // each spoken exactly once: no double-advance
  });

  it("replay repeats the segment then continues", async () => {
    const plan = planOf([seg({ segment_id: "SEG-01", sequence: 1 }), seg({ segment_id: "SEG-02", sequence: 2 })]);
    const spoken: string[] = [];
    let first = true;
    await runPresentation(plan, {
      isAlive: () => true,
      onEvent: () => undefined,
      speakAndWait: async (s) => { spoken.push(s.segment_id); },
      waitTurn: async () => {
        if (first) { first = false; return "replay"; }
        return "next";
      },
    });
    expect(spoken).toEqual(["SEG-01", "SEG-01", "SEG-02"]);
  });

  it("stop aborts with cancellation and never completes", async () => {
    const plan = planOf([seg({ segment_id: "SEG-01", sequence: 1 }), seg({ segment_id: "SEG-02", sequence: 2 })]);
    await expect(runPresentation(plan, {
      isAlive: () => true,
      onEvent: () => undefined,
      speakAndWait: async () => undefined,
      waitTurn: async () => "stop",
    })).rejects.toThrow("__CANCELLED__");
  });

  it("dead session aborts before first segment", async () => {
    const plan = planOf([seg({ segment_id: "SEG-01", sequence: 1 })]);
    const spoken: string[] = [];
    await expect(runPresentation(plan, {
      isAlive: () => false,
      onEvent: () => undefined,
      speakAndWait: async (s) => { spoken.push(s.segment_id); },
      waitTurn: async () => "next",
    })).rejects.toThrow("__CANCELLED__");
    expect(spoken).toEqual([]);
  });
});
