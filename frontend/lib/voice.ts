"use client";

/* TTS/STT abstraction: browser speechSynthesis (hi-IN) + webkit STT, with
   honest fallbacks. No audio is recorded, uploaded or retained. */

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function sttSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

let currentUtter: SpeechSynthesisUtterance | null = null;

export function speak(text: string, opts?: {
  lang?: string; rate?: number; onend?: () => void; onboundary?: () => void;
}): boolean {
  if (!ttsSupported()) return false;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.slice(0, 4000));
    u.lang = opts?.lang ?? "hi-IN";
    u.rate = opts?.rate ?? 0.95;
    if (opts?.onend) u.onend = opts.onend;
    currentUtter = u;
    window.speechSynthesis.speak(u);
    return true;
  } catch {
    return false;
  }
}

export function stopSpeak(): void {
  try {
    window.speechSynthesis?.cancel();
  } catch { /* noop */ }
  currentUtter = null;
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
