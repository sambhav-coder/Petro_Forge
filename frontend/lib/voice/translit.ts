/**
 * Hinglish → Devanagari conversion for HINDI SPEECH QUALITY.
 *
 * Copied from Cyber Sakhi (`sambhav-coder/cyber-sakhi`, `lib/voice/translit.ts`,
 * same author, reused at the owner's request): roman-script Hindi/Hinglish is
 * transliterated to Devanagari BEFORE Hindi-voice synthesis so the hi-IN voice
 * reads natural Hindi instead of letter-spelling. Pragmatic longest-match
 * transliterator with a curated exception dictionary — a categorical
 * improvement over letter-spelling, not a claim of perfect spellings.
 * Devanagari text and non-letter tokens pass through untouched.
 */

const EXCEPTIONS: Record<string, string> = {
  cybercrime: "साइबरक्राइम",
  "cyber-crime": "साइबरक्राइम",
  cyber: "साइबर",
  crime: "क्राइम",
  phishing: "फ़िशिंग",
  scam: "स्कैम",
  fraud: "फ्रॉड",
  hacking: "हैकिंग",
  hacker: "हैकर",
  banking: "बैंकिंग",
  otp: "ओटीपी",
  upi: "यूपीआई",
  bank: "बैंक",
  password: "पासवर्ड",
  internet: "इंटरनेट",
  online: "ऑनलाइन",
  email: "ईमेल",
  account: "अकाउंट",
  number: "नंबर",
  message: "मैसेज",
  phone: "फ़ोन",
  mobile: "मोबाइल",
  money: "पैसे",
  police: "पुलिस",
  lawyer: "वकील",
  app: "ऐप",
  link: "लिंक",
  share: "शेयर",
  block: "ब्लॉक",
  delete: "डिलीट",
  report: "रिपोर्ट",
  dkim: "डीकिम",
  spf: "एसपीएफ़",
  dmarc: "डीमार्क",
  dns: "डीएनएस",
  pump: "पंप",
  steam: "स्टीम",
  pressure: "प्रेशर",
  temperature: "टेम्परेचर",
  production: "प्रोडक्शन",
  simulation: "सिम्युलेशन",
  engineer: "इंजीनियर",
  main: "मैं",
  me: "मैं",
  tum: "तुम",
  aap: "आप",
  hum: "हम",
  woh: "वो",
  wo: "वो",
  yeh: "ये",
  ye: "ये",
  mein: "में",
  se: "से",
  ko: "को",
  ka: "का",
  ki: "की",
  ke: "के",
  na: "ना",
  hai: "है",
  hain: "हैं",
  hoon: "हूँ",
  ho: "हो",
  tha: "था",
  thi: "थी",
  the: "थे",
  gaya: "गया",
  gayi: "गई",
  gaye: "गए",
  diya: "दिया",
  di: "दी",
  kiya: "किया",
  kiye: "किए",
  kya: "क्या",
  kyun: "क्यों",
  kyoon: "क्यों",
  kaise: "कैसे",
  kaisa: "कैसा",
  kab: "कब",
  kahan: "कहाँ",
  karta: "करता",
  karti: "करती",
  karte: "करते",
  karna: "करना",
  karne: "करने",
  karo: "करो",
  kijiye: "कीजिए",
  raha: "रहा",
  rahi: "रही",
  rahe: "रहे",
  sakta: "सकता",
  sakti: "सकती",
  sakte: "सकते",
  chahiye: "चाहिए",
  chahta: "चाहता",
  chahti: "चाहती",
  hota: "होता",
  hoti: "होती",
  hote: "होते",
  bhi: "भी",
  aur: "और",
  toh: "तो",
  to: "तो",
  par: "पर",
  lekin: "लेकिन",
  mat: "मत",
  nahi: "नहीं",
  nahin: "नहीं",
  haan: "हाँ",
  ha: "हाँ",
  ji: "जी",
  mera: "मेरा",
  meri: "मेरी",
  mere: "मेरे",
  tera: "तेरा",
  teri: "तेरी",
  hamara: "हमारा",
  naam: "नाम",
  baat: "बात",
  acha: "अच्छा",
  achha: "अच्छा",
  accha: "अच्छा",
  achhi: "अच्छी",
  achhe: "अच्छे",
  theek: "ठीक",
  thik: "ठीक",
  galat: "गलत",
  sahi: "सही",
  surakshit: "सुरक्षित",
  khatra: "खतरा",
  bahut: "बहुत",
  thoda: "थोड़ा",
  thodi: "थोड़ी",
  jyada: "ज़्यादा",
  kam: "कम",
  sab: "सब",
  sabse: "सबसे",
  apna: "अपना",
  apni: "अपनी",
  apne: "अपने",
  dost: "दोस्त",
  samajh: "समझ",
  samajho: "समझो",
  dekho: "देखो",
  dekha: "देखा",
  suno: "सुनो",
  suna: "सुना",
  bolo: "बोलो",
  bola: "बोला",
  bolna: "बोलना",
  sath: "साथ",
  saath: "साथ",
  pyaar: "प्यार",
  mila: "मिला",
  milta: "मिलता",
  aata: "आता",
  usse: "उसे",
  isse: "इसे",
  yahan: "यहाँ",
  wahan: "वहाँ",
  abhi: "अभी",
  kal: "कल",
  aaj: "आज",
  duniya: "दुनिया",
  koi: "कोई",
  kisi: "किसी",
  kuch: "कुछ",
  alag: "अलग",
  batao: "बताओ",
  jao: "जाओ",
  khao: "खाओ",
  banao: "बनाओ",
  bulao: "बुलाओ",
  sunao: "सुनाओ",
  aao: "आओ",
  karao: "कराओ",
  crack: "क्रैक",
  black: "ब्लैक",
  attack: "अटैक",
  lock: "लॉक",
  track: "ट्रैक",
  back: "बैक",
  kon: "कौन",
};

const VOWELS: Array<[string, { standalone: string; matra: string }]> = [
  ["aa", { standalone: "आ", matra: "ा" }],
  ["ee", { standalone: "ई", matra: "ी" }],
  ["oo", { standalone: "ऊ", matra: "ू" }],
  ["ai", { standalone: "ऐ", matra: "ै" }],
  ["au", { standalone: "औ", matra: "ौ" }],
  ["ri", { standalone: "ऋ", matra: "ृ" }],
  ["a", { standalone: "अ", matra: "" }],
  ["e", { standalone: "ए", matra: "े" }],
  ["i", { standalone: "इ", matra: "ि" }],
  ["o", { standalone: "ओ", matra: "ो" }],
  ["u", { standalone: "उ", matra: "ु" }],
];

const CONSONANTS: Array<[string, string]> = [
  ["str", "स्" + "त्र"],
  ["shr", "श्र"],
  ["ksh", "क्ष"],
  ["chh", "छ"],
  ["ch", "च"],
  ["kh", "ख"],
  ["gh", "घ"],
  ["jh", "झ"],
  ["th", "थ"],
  ["dh", "ध"],
  ["bh", "भ"],
  ["ph", "फ"],
  ["sh", "श"],
  ["gy", "ज्ञ"],
  ["tr", "त्र"],
  ["dr", "द्र"],
  ["pr", "प्र"],
  ["br", "ब्र"],
  ["kr", "क्र"],
  ["gr", "ग्र"],
  ["ng", "ङ"],
  ["k", "क"],
  ["g", "ग"],
  ["c", "च"],
  ["j", "ज"],
  ["z", "ज़"],
  ["t", "त"],
  ["d", "द"],
  ["n", "न"],
  ["p", "प"],
  ["f", "फ़"],
  ["b", "ब"],
  ["m", "म"],
  ["y", "य"],
  ["r", "र"],
  ["l", "ल"],
  ["v", "व"],
  ["w", "व"],
  ["s", "स"],
  ["h", "ह"],
  ["x", "क्स"],
  ["q", "क़"],
];

const STOPS = /[kgcjtdpb]/;

const ITRANS_PRE: Array<[RegExp, string]> = [
  [/[āĀ]/g, "aa"],
  [/[īĪ]/g, "ee"],
  [/[ūŪ]/g, "oo"],
  [/[ṛ]/g, "r"],
  [/[ṭ]/g, "t"],
  [/[ḍ]/g, "d"],
  [/[ṅ]/g, "n"],
  [/[ñ]/g, "n"],
  [/[ṇ]/g, "n"],
  [/[ś]/g, "sh"],
  [/[ṣ]/g, "sh"],
  [/[ḥ]/g, "h"],
  [/[ṃṁ]/g, "n"],
];

const DEVA_ASCII = /[A-Za-z]/;

interface Syllable {
  consonants: string[];
  vowel: string;
}

const isVowelChar = (ch: string): boolean =>
  ch === "a" || ch === "e" || ch === "i" || ch === "o" || ch === "u";

function readVowel(word: string, i: number): { tok: string; next: number } {
  for (const [tok] of VOWELS) {
    if (word.startsWith(tok, i)) return { tok, next: i + tok.length };
  }
  if (isVowelChar(word[i])) return { tok: word[i], next: i + 1 };
  return { tok: "", next: i };
}

function readConsonant(word: string, i: number): { ch: string; next: number } {
  for (const [seq] of CONSONANTS) {
    if (word.startsWith(seq, i)) return { ch: seq, next: i + seq.length };
  }
  const c = word[i];
  if (DEVA_ASCII.test(c)) return { ch: c, next: i + 1 };
  return { ch: "", next: i };
}

function syllabify(word: string): Syllable[] {
  const out: Syllable[] = [];
  let i = 0;
  if (word.length === 0) return out;
  if (isVowelChar(word[0])) {
    const v = readVowel(word, 0);
    out.push({ consonants: [], vowel: v.tok });
    i = v.next;
  }
  while (i < word.length && DEVA_ASCII.test(word[i])) {
    const c = readConsonant(word, i);
    if (c.ch && !isVowelChar(c.ch)) {
      i = c.next;
      const v = readVowel(word, i);
      const hasVowel = v.tok !== "";
      out.push({ consonants: [c.ch], vowel: hasVowel ? v.tok : "" });
      i = hasVowel ? v.next : i;
      continue;
    }
    const v = readVowel(word, i);
    if (v.tok) {
      out.push({ consonants: [], vowel: v.tok });
      i = v.next;
      continue;
    }
    i += 1;
  }
  return out;
}

function wordToDevanagari(word: string): string {
  if (word.length === 0) return "";
  if (EXCEPTIONS[word]) return EXCEPTIONS[word];
  const syl = syllabify(word);
  if (syl.length === 0) return word;

  const n = syl.length;
  let out = "";
  for (let k = 0; k < n; k += 1) {
    const s = syl[k];
    const cs = s.consonants;
    const isLast = k === n - 1;
    let vowel = s.vowel;
    if (isLast) {
      if (vowel === "a") vowel = "aa";
      else if (vowel === "i") vowel = "ee";
    }

    if (cs.length === 0) {
      const v = VOWELS.find(([t]) => t === s.vowel);
      out += (v && v[1].standalone) || "";
      continue;
    }

    for (let ci = 0; ci < cs.length; ci += 1) {
      const c = cs[ci];
      const isFinalConsonant = ci === cs.length - 1;
      const followedByStop =
        s.vowel === "" &&
        k + 1 < n &&
        syl[k + 1].consonants.length > 0 &&
        STOPS.test(syl[k + 1].consonants[0] || "");
      const nasalBeforeStop = (c === "n" || c === "m") && followedByStop;
      let letter = CONSONANTS.find(([seq]) => seq === c)?.[1] || "";
      if (nasalBeforeStop) {
        letter = "ं";
      }
      out += letter;
      if (!isFinalConsonant && !nasalBeforeStop) out += "्";
    }

    if (vowel && vowel !== "a") {
      const v = VOWELS.find(([t]) => t === vowel);
      out += (v && v[1].matra) || "";
    }
  }
  return out;
}

/**
 * Convert roman (Hinglish/English) script inside `text` to Devanagari.
 * Devanagari segments, numbers, URLs, and punctuation pass through untouched.
 */
export function hinglishToDevanagari(text: string): string {
  if (!text || !DEVA_ASCII.test(text)) return text;
  let t = text;
  for (const [re, sub] of ITRANS_PRE) t = t.replace(re, sub);

  const TOKEN = /([\u0900-\u097F]+)|([A-Za-z]+)|([^A-Za-z\u0900-\u097F]+)/g;
  const pieces: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = TOKEN.exec(t)) !== null) {
    if (m[2]) {
      pieces.push(tokenToDevanagari(m[2]));
    } else {
      pieces.push(m[0]);
    }
  }
  return pieces.join("");
}

function tokenToDevanagari(token: string): string {
  return token
    .split(/([0-9]+)/g)
    .map((part) =>
      part && DEVA_ASCII.test(part) && !/[0-9]/.test(part)
        ? wordToDevanagari(part.toLowerCase())
        : part
    )
    .join("");
}

/** Prep roman Hindi for Devanagari speech reading. */
export function prepForHindiSpeech(text: string): string {
  return hinglishToDevanagari(text);
}
