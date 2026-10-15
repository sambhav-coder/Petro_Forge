/**
 * Authoritative server-side Co-Pilot voice configuration.
 *
 * Ported from Cyber Sakhi (`sambhav-coder/cyber-sakhi`, `lib/voice/voices.ts`)
 * — same Edge TTS engine, same voice IDs — with Cyber Sakhi-specific naming
 * adapted to PetroForge. Rules preserved from the source:
 * - Language follows the ACTUAL turn language (en | hi | hinglish); Hinglish
 *   uses the Hindi voice by design.
 * - No silent fallback to an unrelated voice: unknown languages throw so the
 *   failure surfaces upstream (client engine then uses its explicit
 *   browser-voice fallback path and reports it via onError).
 * - No secrets in this file.
 *
 * Exact voices (verified in source repo history and voice tests):
 *   en       -> en-IN-NeerjaNeural (lang en-IN)
 *   hi       -> hi-IN-SwaraNeural  (lang hi-IN)
 *   hinglish -> hi-IN-SwaraNeural  (lang hi-IN)
 */

export type CopilotVoiceLanguage = "en" | "hi" | "hinglish";

export interface ServerVoiceConfig {
  voice: string;
  lang: string;
}

export const COPILOT_SERVER_VOICES: Record<CopilotVoiceLanguage, ServerVoiceConfig> = {
  en: { voice: "en-IN-NeerjaNeural", lang: "en-IN" },
  hi: { voice: "hi-IN-SwaraNeural", lang: "hi-IN" },
  hinglish: { voice: "hi-IN-SwaraNeural", lang: "hi-IN" },
};

export function normalizeVoiceLanguage(language: string): CopilotVoiceLanguage {
  const normalized = String(language || "").trim().toLowerCase();
  if (normalized === "hi" || normalized === "hinglish") return normalized;
  if (normalized === "en") return "en";
  throw new Error(
    `Unknown voice language "${language}". Detect the turn language (en/hi/hinglish) before requesting speech.`
  );
}

/** Resolve the exact server voice for a turn language. Throws on unknown. */
export function resolveServerVoice(language: string): ServerVoiceConfig {
  return COPILOT_SERVER_VOICES[normalizeVoiceLanguage(language)];
}
