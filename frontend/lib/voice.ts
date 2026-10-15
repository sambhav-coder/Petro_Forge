"use client";

/**
 * Co-Pilot voice engine: exact Cyber Sakhi pipeline.
 *
 * Speech path (ported from `sambhav-coder/cyber-sakhi`,
 * `lib/voice/speech.ts` → `speakWithEngine`):
 *  1. Server Edge TTS first — en-IN-NeerjaNeural for English turns,
 *     hi-IN-SwaraNeural for Hindi/Hinglish turns (see `lib/voice/voices.ts`),
 *     via POST /api/voice/tts returning base64 MP3 (+ word timings).
 *  2. Per-chunk HTMLAudio playback; the NEXT chunk starts only on the audio
 *     `ended` event — never on play-request. A failed/blocked request is
 *     reported via onError and never counted as completed.
 *  3. First-chunk server failure → browser speechSynthesis fallback with a
 *     pre-resolved female voice (hi turns transliterated to Devanagari via
 *     `lib/voice/translit.ts`, same as the source).
 * STT stays on-device browser SpeechRecognition (same policy as the source:
 * no local Python engines, mic only after explicit user action, nothing
 * uploaded). No API keys anywhere — Edge TTS needs none; nothing secret is
 * exposed to the browser.
 */

import { hinglishToDevanagari } from "./voice/translit";

export type VoiceLanguage = "en" | "hi" | "hinglish";

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && ("speechSynthesis" in window || true);
}

export function sttSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export function warmVoices(): void {
  try {
    window.speechSynthesis?.getVoices();
    if (typeof window.speechSynthesis !== "undefined") {
      window.speechSynthesis.onvoiceschanged = () => {
        try { window.speechSynthesis.getVoices(); } catch { /* noop */ }
      };
    }
  } catch { /* noop */ }
}

/* Keep technical abbreviations speakable; full normalization happens server-side. */
export function normalizeForSpeech(text: string): string {
  let t = (text || "").replace(/\s+/g, " ").trim();
  const subs: Array<[RegExp, string]> = [
    [/\bbopd\b/g, "B O P D"],
    [/\bSPM\b/g, "S P M"],
    [/\bSOR\b/g, "S O R"],
    [/\bCSS\b/g, "C S S"],
    [/\bSRP\b/g, "S R P"],
    [/\bVFD\b/g, "V F D"],
    [/\bkWh\b/g, "kilowatt hour"],
    [/\bCWE\b/g, "C W E"],
  ];
  for (const [re, rep] of subs) t = t.replace(re, rep);
  return t;
}

/** Sentence-aware chunks for the server (≤1500 chars like the source). */
export function chunkForSpeech(text: string, maxLen = 1500): string[] {
  const clean = normalizeForSpeech(text);
  if (!clean) return [];
  if (clean.length <= maxLen) return [clean];
  const parts = clean.split(/(?<=[.!?।])\s+/);
  const chunks: string[] = [];
  let buf = "";
  for (const p of parts) {
    if ((buf + " " + p).trim().length <= maxLen) buf = (buf + " " + p).trim();
    else { if (buf) chunks.push(buf); buf = p.length <= maxLen ? p : p.slice(0, maxLen); }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

/* ---------- browser fallback voice resolution (source: speech.ts) ---------- */

const STRONG_FEMALE = [
  /female/i, /\bzira\b/i, /\bsamantha\b/i, /\bveena\b/i, /\bheera\b/i,
  /\bswara\b/i, /\bneerja\b/i, /\bjenny\b/i, /\bava\b/i, /\bemma\b/i,
  /\bnatasha\b/i, /\baria\b/i, /\bgoogle\s*uk\s*english\s*female/i,
  /\bgoogle\s*us\s*english\b/i,
];
const MALE = [/\bmale\b/i, /\bdavid\b/i, /\bmark\b/i, /\brahul\b/i, /\barjun\b/i, /\bgoogle\s*uk\s*english\s*male/i];

function scoreVoice(name: string): number {
  let s = 0;
  for (const m of STRONG_FEMALE) if (m.test(name)) s += 3;
  for (const m of MALE) if (m.test(name)) s -= 5;
  return s;
}

export async function resolveFemaleVoice(lang: VoiceLanguage = "hinglish"): Promise<SpeechSynthesisVoice | null> {
  try {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
    const synth = window.speechSynthesis;
    let voices = synth.getVoices();
    if (!voices.length) {
      voices = await new Promise<SpeechSynthesisVoice[]>((res) => {
        const to = setTimeout(() => res(synth.getVoices() || []), 2000);
        try {
          synth.onvoiceschanged = () => { clearTimeout(to); res(synth.getVoices() || []); };
        } catch { clearTimeout(to); res(synth.getVoices() || []); }
      });
    }
    const target = lang === "en" ? "en" : "hi";
    const ranked = voices
      .map((v) => ({ v, s: scoreVoice(v.name || "") }))
      .sort((a, b) => {
        const la = (a.v.lang || "").toLowerCase().startsWith(target) ? 1 : 0;
        const lb = (b.v.lang || "").toLowerCase().startsWith(target) ? 1 : 0;
        return lb - la || b.s - a.s;
      });
    return ranked.length ? ranked[0].v : null;
  } catch {
    return null;
  }
}

function speakBrowserChunks(
  texts: string[],
  voice: SpeechSynthesisVoice | null,
  lang: VoiceLanguage,
  rate: number,
  isAlive: () => boolean,
  onDone: () => void,
  onError: (m: string) => void
): () => void {
  let cancelled = false;
  let i = 0;
  const synth = window.speechSynthesis;
  const next = () => {
    if (cancelled || !isAlive()) return;
    if (i >= texts.length) { onDone(); return; }
    const raw = texts[i];
    i += 1;
    const eff = lang === "hi" || lang === "hinglish" ? hinglishToDevanagari(raw) : raw;
    const u = new SpeechSynthesisUtterance(eff);
    if (voice) {
      const hiCapable = String(voice.lang || "").toLowerCase().startsWith("hi");
      if (lang === "en" || hiCapable) u.voice = voice;
    }
    u.lang = lang === "en" ? "en-IN" : "hi-IN";
    u.rate = rate;
    u.pitch = 1.05;
    u.onend = () => { if (!cancelled) setTimeout(next, 0); };
    u.onerror = () => { if (!cancelled) { cancelled = true; onError("Voice playback stopped (browser error or mute)."); } };
    try {
      if (synth.paused) synth.resume();
      synth.speak(u);
    } catch {
      cancelled = true;
      onError("Voice playback failed.");
    }
  };
  next();
  return () => { cancelled = true; try { synth.cancel(); } catch { /* noop */ } };
}

/* ---------- engine: server Edge TTS first, browser fallback ---------- */

export interface EngineHandle {
  cancel: () => void;
  pause: () => void;
  resume: () => void;
}

async function fetchTtsChunk(text: string, language: VoiceLanguage): Promise<
  | { ok: true; audioUrl: string; voice: string }
  | { ok: false; code: string }
> {
  try {
    const res = await fetch("/api/voice/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data || data.available !== true || !data.audioB64) {
      return { ok: false, code: data?.code || "tts_unavailable" };
    }
    const bin = atob(data.audioB64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const audioUrl = URL.createObjectURL(new Blob([bytes], { type: data.mimeType || "audio/mpeg" }));
    return { ok: true, audioUrl, voice: data.voice || "" };
  } catch {
    return { ok: false, code: "network" };
  }
}

/**
 * Speak full text through the Edge TTS queue. `onDone` fires ONLY after the
 * final chunk's audio `ended` (or the browser-fallback queue drains) — a
 * play request alone never completes the turn. Returns pause/resume/cancel.
 */
export function speakQueue(
  text: string,
  opts?: {
    lang?: string; rate?: number; language?: VoiceLanguage;
    onDone?: () => void; onError?: (m: string) => void;
    onChunk?: (i: number, n: number) => void;
  }
): EngineHandle {
  const language: VoiceLanguage =
    opts?.language ?? (opts?.lang === "hi-IN" || opts?.lang === "hi" ? "hi" : "hinglish");
  const rate = opts?.rate ?? 1;
  let cancelled = false;
  let paused = false;
  let currentAudio: HTMLAudioElement | null = null;
  let cancelBrowser: (() => void) | null = null;
  const isAlive = () => !cancelled;



  const self: EngineHandle = {
    cancel: () => {
      cancelled = true;
      cancelBrowser?.();
      try { if (currentAudio) currentAudio.pause(); } catch { /* noop */ }
      currentAudio = null;
      if (activeHandle === self) activeHandle = null;
    },
    pause: () => {
      paused = true;
      try {
        if (currentAudio && !currentAudio.paused) currentAudio.pause();
        else pauseSpeak();
      } catch { /* noop */ }
    },
    resume: () => {
      if (!paused) return;
      paused = false;
      try {
        if (currentAudio && currentAudio.paused) { void currentAudio.play(); }
        else resumeSpeak();
      } catch { /* noop */ }
    },
  };
  trackHandle(self);

  const done = () => { if (activeHandle === self) activeHandle = null; if (!cancelled) { const cb = opts?.onDone; if (cb) cb(); } };
  const fail = (m: string) => { if (!cancelled) { const cb = opts?.onError; if (cb) cb(m); } };

  void (async () => {
    if (cancelled) return;
    const chunks = chunkForSpeech(text).filter(Boolean);
    if (!chunks.length) { done(); return; }

    for (let i = 0; i < chunks.length; i++) {
      if (cancelled) return;
      opts?.onChunk?.(i, chunks.length);
      const srv = await fetchTtsChunk(chunks[i], language);
      if (cancelled) { if (srv.ok) URL.revokeObjectURL(srv.audioUrl); return; }
      if (!srv.ok) {
        if (i === 0) {
          // First-chunk server failure → explicit browser fallback (reported).
          fail("Server voice unavailable — using on-device voice.");
          const voice = await resolveFemaleVoice(language);
          if (cancelled) return;
          cancelBrowser = speakBrowserChunks(chunks, voice, language, rate, isAlive, done, fail);
        } else {
          fail("Voice could not finish aloud.");
        }
        return;
      }
      const el = new Audio();
      currentAudio = el;
      el.src = srv.audioUrl;
      el.playbackRate = rate;
      try {
        await el.play();
      } catch {
        URL.revokeObjectURL(srv.audioUrl);
        currentAudio = null;
        if (i === 0) {
          fail("Voice playback blocked — using on-device voice.");
          const voice = await resolveFemaleVoice(language);
          if (cancelled) return;
          cancelBrowser = speakBrowserChunks(chunks, voice, language, rate, isAlive, done, fail);
        } else {
          fail("Voice playback was blocked by the browser.");
        }
        return;
      }
      if (cancelled) { el.pause(); URL.revokeObjectURL(srv.audioUrl); return; }
      await new Promise<void>((resolve) => {
        el.addEventListener("ended", () => resolve(), { once: true });
        el.addEventListener("error", () => { fail("Voice playback stopped."); resolve(); }, { once: true });
      });
      URL.revokeObjectURL(srv.audioUrl);
      currentAudio = null;
      if (cancelled) return;
    }
    done();
  })();

  return self;
}

/** Backwards-compatible single-shot speak. */
export function speak(text: string, opts?: {
  lang?: string; rate?: number; onend?: () => void; onboundary?: () => void;
}): boolean {
  if (typeof window === "undefined") return false;
  speakQueue(text, { lang: opts?.lang, rate: opts?.rate, onDone: opts?.onend ?? undefined });
  return true;
}

let legacyHandle: EngineHandle | null = null;
let activeHandle: EngineHandle | null = null;

function trackHandle(h: EngineHandle): EngineHandle {
  activeHandle = h;
  return h;
}

export function stopQueue(): void {
  activeHandle?.cancel();
  activeHandle = null;
  legacyHandle?.cancel();
  legacyHandle = null;
  try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
}

export function stopSpeak(): void {
  stopQueue();
}

export function pauseSpeak(): boolean {
  if (activeHandle) { activeHandle.pause(); return true; }
  try {
    if (window.speechSynthesis?.speaking && !window.speechSynthesis.paused) {
      window.speechSynthesis.pause();
      return true;
    }
  } catch { /* noop */ }
  return false;
}

export function resumeSpeak(): boolean {
  if (activeHandle) { activeHandle.resume(); return true; }
  try {
    if (window.speechSynthesis?.paused) {
      window.speechSynthesis.resume();
      return true;
    }
  } catch { /* noop */ }
  return false;
}

/** One-shot voice question (mic only after explicit user click). */
export function listenOnce(opts?: { lang?: string; timeoutMs?: number }): Promise<string | null> {
  return new Promise((resolve) => {
    if (!sttSupported()) { resolve(null); return; }
    try {
      const w = window as unknown as {
        SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any;
      };
      const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
      if (!Ctor) { resolve(null); return; }
      const rec = new Ctor();
      rec.lang = opts?.lang ?? "hi-IN";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      let done = false;
      const finish = (v: string | null) => { if (!done) { done = true; try { rec.stop(); } catch { /* noop */ } resolve(v); } };
      rec.onresult = (e: any) => finish(e?.results?.[0]?.[0]?.transcript ?? null);
      rec.onerror = () => finish(null);
      rec.onend = () => finish(null);
      rec.start();
      setTimeout(() => finish(null), opts?.timeoutMs ?? 15000);
    } catch {
      resolve(null);
    }
  });
}
