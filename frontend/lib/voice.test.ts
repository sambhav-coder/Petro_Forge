import { describe, expect, it } from "vitest";
import { chunkForSpeech, normalizeForSpeech } from "./voice";
import { COPILOT_SERVER_VOICES, normalizeVoiceLanguage, resolveServerVoice } from "./voice/voices";

describe("voice text preparation", () => {
  it("expands technical abbreviations and keeps numbers", () => {
    const t = normalizeForSpeech("Pump at 5 SPM, SOR 0.1, 22.5 bopd, CSS soak");
    expect(t).toContain("S P M");
    expect(t).toContain("S O R");
    expect(t).toContain("B O P D");
    expect(t).toContain("C S S");
    expect(t).toContain("22.5");
  });

  it("chunks long narration into bounded ordered pieces", () => {
    const long = Array.from({ length: 12 }, (_, i) => `Sentence number ${i} explains the pump unit clearly.`).join(" ");
    const chunks = chunkForSpeech(long, 200);
    expect(chunks.length).toBeGreaterThan(2);
    expect(chunks.every((c) => c.length <= 220)).toBe(true);
    expect(chunks.join(" ")).toBe(long.replace(/\s+/g, " ").trim());
  });
});

describe("authoritative server voices (Cyber Sakhi parity)", () => {
  it("pins the exact Edge TTS voice IDs", () => {
    expect(COPILOT_SERVER_VOICES.en).toEqual({ voice: "en-IN-NeerjaNeural", lang: "en-IN" });
    expect(COPILOT_SERVER_VOICES.hi).toEqual({ voice: "hi-IN-SwaraNeural", lang: "hi-IN" });
    expect(COPILOT_SERVER_VOICES.hinglish).toEqual({ voice: "hi-IN-SwaraNeural", lang: "hi-IN" });
  });

  it("resolves hinglish to the Hindi voice and throws on unknown", () => {
    expect(resolveServerVoice("hinglish").voice).toBe("hi-IN-SwaraNeural");
    expect(normalizeVoiceLanguage("hi")).toBe("hi");
    expect(() => normalizeVoiceLanguage("french")).toThrow();
  });
});
