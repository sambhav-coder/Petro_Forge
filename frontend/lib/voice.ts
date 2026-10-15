"use client";

/* TTS/STT abstraction: hi-IN speechSynthesis with voice selection, speech-aware
   chunked queue playback, plus webkit STT. No audio recorded/uploaded/retained.

   Cyber Sakhi reference repository was NOT accessible in this workspace (no
   local checkout found), so no voice pipeline was copied from it. This module
   is an independent provider-agnostic upgrade: deterministic text
   normalization + sentence-aware chunking + completion-driven queue, ready to
   bind a server-side neural provider later without changing callers. */

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function sttSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

function pickHindiVoice(): SpeechSynthesisVoice | null {
  try {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    const score = (v: SpeechSynthesisVoice): number => {
      const l = (v.lang || "").toLowerCase();
      const n = (v.name || "").toLowerCase();
      let s = 0;
      if (l.startsWith("hi")) s += 10;
      if (l === "hi-in") s += 4;
      if (n.includes("hindi")) s += 4;
      if (n.includes("google")) s += 2;
      if (n.includes("female") || n.includes("lekha") || n.includes("kalpana")) s += 2;
      if (v.default) s += 1;
      if (v.localService) s += 1;
      return s;
    };
    return [...voices].sort((a, b) => score(b) - score(a))[0] ?? null;
  } catch {
    return null;
  }
}

export function warmVoices(): void {
  // Voices load async in some browsers; prime the list early.
  try {
    window.speechSynthesis?.getVoices();
    if (typeof window.speechSynthesis !== "undefined") {
      window.speechSynthesis.onvoiceschanged = () => {
        try { window.speechSynthesis.getVoices(); } catch { /* noop */ }
      };
    }
  } catch { /* noop */ }
}

/* Expand abbreviations for understandable speech; keep numbers/issue as-is. */
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

/** Split long explanations into short speakable chunks (sentence-aware). */
export function chunkForSpeech(text: string, maxLen = 200): string[] {
  const sentences = text.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
  const chunks: string[] = [];
  let buf = "";
  for (const s of sentences) {
    if ((buf + " " + s).trim().length <= maxLen) {
      buf = (buf + " " + s).trim();
    } else {
      if (buf) chunks.push(buf);
      if (s.length <= maxLen) {
        buf = s;
      } else {
        // Hard-split overlong sentence on commas.
        const parts = s.split(/,\s*/);
        buf = "";
        for (const p of parts) {
          if ((buf + ", " + p).length <= maxLen) buf = buf ? buf + ", " + p : p;
          else { if (buf) chunks.push(buf); buf = p; }
        }
      }
    }
  }
  if (buf) chunks.push(buf);
  return chunks.length > 0 ? chunks : [text];
}

interface QueueState {
  active: boolean;
  cancelled: boolean;
  onDone: (() => void) | null;
}

const queue: QueueState = { active: false, cancelled: false, onDone: null };

/** Speak full text as a completion-chained chunk queue. onDone fires once. */
export function speakQueue(text: string, opts?: {
  lang?: string; rate?: number; onDone?: () => void; onChunk?: (i: number, n: number) => void;
}): boolean {
  if (!ttsSupported()) return false;
  stopQueue();
  const chunks = chunkForSpeech(normalizeForSpeech(text)).filter(Boolean);
  if (chunks.length === 0) return false;
  queue.active = true;
  queue.cancelled = false;
  queue.onDone = opts?.onDone ?? null;
  const voice = pickHindiVoice();
  let i = 0;
  const next = () => {
    if (queue.cancelled || !queue.active) return;
    if (i >= chunks.length) {
      queue.active = false;
      const cb = queue.onDone;
      queue.onDone = null;
      cb?.();
      return;
    }
    try {
      const u = new SpeechSynthesisUtterance(chunks[i]);
      u.lang = opts?.lang ?? "hi-IN";
      u.rate = opts?.rate ?? 0.95;
      if (voice) u.voice = voice;
      opts?.onChunk?.(i, chunks.length);
      u.onend = () => { i += 1; next(); };
      u.onerror = () => { i += 1; next(); }; // audio error never blocks presentation
      window.speechSynthesis.speak(u);
    } catch {
      i += 1;
      next();
    }
  };
  next();
  return true;
}

/** Backwards-compatible single-shot speak (uses queue internally). */
export function speak(text: string, opts?: {
  lang?: string; rate?: number; onend?: () => void; onboundary?: () => void;
}): boolean {
  return speakQueue(text, { lang: opts?.lang, rate: opts?.rate, onDone: opts?.onend ?? undefined });
}

export function stopQueue(): void {
  queue.cancelled = true;
  queue.active = false;
  queue.onDone = null;
  try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
}

export function stopSpeak(): void {
  stopQueue();
}

export function pauseSpeak(): boolean {
  try {
    if (window.speechSynthesis?.speaking && !window.speechSynthesis.paused) {
      window.speechSynthesis.pause();
      return true;
    }
  } catch { /* noop */ }
  return false;
}

export function resumeSpeak(): boolean {
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
