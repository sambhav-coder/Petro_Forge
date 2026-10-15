import { NextRequest, NextResponse } from "next/server";
import { synthesizeWithEdgeTTS } from "@/lib/voice/edgeTts";
import { normalizeVoiceLanguage } from "@/lib/voice/voices";

/**
 * POST /api/voice/tts — server-side Edge TTS for the AI Co-Pilot.
 *
 * Ported from Cyber Sakhi (`sambhav-coder/cyber-sakhi`,
 * `app/api/voice/tts/route.ts`): same engine (node-edge-tts, no API key),
 * same voices (en-IN-NeerjaNeural / hi-IN-SwaraNeural), same sanitization
 * and base64-MP3 contract. Difference: PetroForge has no auth system, so this
 * route is unauthenticated and rate-limited by text length (2000 chars) like
 * the source. No secrets involved — Edge TTS needs no key.
 */

const MARKDOWN_STRIP = /[*_`#>|~]/g;
const CONTROL_STRIP = /[\u0000-\u001f\u007f]/g;

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const rawText =
      typeof body.text === "string" ? body.text.slice(0, 2000) : "";

    const text = rawText
      .replace(MARKDOWN_STRIP, "")
      .replace(CONTROL_STRIP, "")
      .replace(/\n{2,}/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();

    if (!text) {
      return NextResponse.json(
        { available: false, code: "tts_no_text", note: "No text provided." },
        { status: 400 }
      );
    }

    let language;
    try {
      language = normalizeVoiceLanguage(body.language ?? "hinglish");
    } catch {
      language = "hinglish" as const;
    }

    const audio = await synthesizeWithEdgeTTS(text, language);

    return NextResponse.json({
      available: true,
      audioB64: audio.buffer.toString("base64"),
      mimeType: audio.mimeType,
      voice: audio.voice,
      language,
      words: audio.words || [],
    });
  } catch (error) {
    console.error("[TTS API] synthesis failed:", error);
    return NextResponse.json(
      {
        available: false,
        code: "tts_error",
        note:
          error instanceof Error ? error.message : "Speech synthesis failed.",
      },
      { status: 500 }
    );
  }
}
