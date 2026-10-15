// Voice acceptance sample: representative Hinglish technical narration.
// Run: node scripts/voice-acceptance.mjs (needs network to Edge TTS).
process.env.WS_NO_BUFFER_UTIL = "1";
const { EdgeTTS } = await import("node-edge-tts");

const samples = [
  ["hinglish", "hi-IN-SwaraNeural", "Namaste, engineer. Main selected well ka available data analyze kar raha hoon."],
  ["hinglish", "hi-IN-SwaraNeural", "Ab hum S R P ke upstroke ko dekh rahe hain. Pump efficiency aur dynamometer card ke numbers validated backend output se liye gaye hain."],
  ["hinglish", "hi-IN-SwaraNeural", "Steam injection, soak period aur production cycle ke baad, steam-oil ratio zero point one hai."],
];

for (const [lang, voice, text] of samples) {
  const out = `voice-sample-${lang}-${Date.now()}.mp3`;
  try {
    const tts = new EdgeTTS({ voice, lang: voice.slice(0, 5), outputFormat: "audio-24khz-96kbitrate-mono-mp3", timeout: 30000 });
    await tts.ttsPromise(text, out);
    const fs = await import("fs");
    const size = fs.statSync(out).size;
    console.log("OK", voice, size, "bytes ->", out);
    fs.unlinkSync(out);
  } catch (e) {
    console.log("FAIL", voice, String(e).slice(0, 200));
    process.exitCode = 1;
  }
}
