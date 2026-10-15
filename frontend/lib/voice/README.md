# Co-Pilot voice pipeline — provenance and contract

Source: `sambhav-coder/cyber-sakhi` (same owner, reused at the owner's request).

## What was reused (adapted naming only)
- `lib/voice/voices.ts` ← `lib/voice/voices.ts`: exact Edge TTS voice IDs.
- `lib/voice/edgeTts.ts` ← `lib/voice/edgeTts.ts`: `node-edge-tts` synthesis,
  MP3 format, subtitle timings, ws-bundling workaround, Vercel `/tmp` handling.
- `lib/voice/translit.ts` ← `lib/voice/translit.ts`: Hinglish→Devanagari for
  the browser fallback (plus a few PetroForge-domain words: pump, steam…).
- `app/api/voice/tts/route.ts` ← `app/api/voice/tts/route.ts`: sanitize,
  2000-char cap, base64-MP3 + word timings contract.
- Client engine semantics ← `lib/voice/speech.ts` `speakWithEngine`:
  server-first per-chunk audio queue chained on `ended`, first-chunk failure →
  pre-resolved female browser voice, errors never reported as complete.
- Unrelated Cyber Sakhi features (auth, RAG, cases, blockchain) NOT copied.

## Exact voices
- English turns → `en-IN-NeerjaNeural` (`en-IN`)
- Hindi/Hinglish turns → `hi-IN-SwaraNeural` (`hi-IN`)

## Differences from the source
- No NextAuth in PetroForge: the TTS route is unauthenticated (text-length
  capped). No secrets involved — Edge TTS requires no API key.
- STT stays on-device browser SpeechRecognition (same policy as source).

## Dependencies / licensing
- `node-edge-tts` (MIT, see `node_modules/node-edge-tts/LICENSE`). Uses the
  public Microsoft Edge TTS endpoint (network required; subject to
  Microsoft's service terms).
- No credentials, no `.env` entries required for voice.

## Verification
- `node scripts/voice-acceptance.mjs` synthesizes 3 Hinglish technical samples
  via `hi-IN-SwaraNeural` (network required). Listening-quality evaluation
  needs a human ear and is NOT claimed from byte counts.
