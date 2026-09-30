import path from "node:path";
import type { Config } from "tailwindcss";

const src = (p: string) => path.join(__dirname, p).replace(/\\/g, "/");

const config: Config = {
  content: [src("app/**/*.{ts,tsx}"), src("components/**/*.{ts,tsx}"), src("lib/**/*.{ts,tsx}")],
  theme: {
    extend: {
      colors: {
        oil: {
          black: "#07100D",
          deep: "#0A1A14",
        },
        forest: {
          deep: "#0B241A",
          DEFAULT: "#123F2A",
        },
        petroleum: {
          DEFAULT: "#123F2A",
          light: "#1F6B45",
        },
        natural: {
          DEFAULT: "#3FA66B",
        },
        crude: {
          DEFAULT: "#5A3A24",
        },
        earth: {
          DEFAULT: "#7A5234",
          deep: "#3d2a18",
        },
        sand: {
          DEFAULT: "#C6A878",
        },
        amber: {
          warm: "#D99A3D",
        },
        cream: {
          soft: "#E8DDC8",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        display: ['"Space Grotesk"', "Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "petro-gradient":
          "linear-gradient(135deg, #0B241A 0%, #123F2A 45%, #5A3A24 100%)",
        "petro-gradient-soft":
          "linear-gradient(135deg, rgba(11,36,26,0.85) 0%, rgba(18,63,42,0.7) 45%, rgba(90,58,36,0.6) 100%)",
        "text-gradient":
          "linear-gradient(135deg, #3FA66B 0%, #D99A3D 50%, #E8DDC8 100%)",
        "glass-gradient":
          "linear-gradient(180deg, rgba(11,36,26,0.72) 0%, rgba(7,16,13,0.88) 100%)",
        "border-gradient":
          "linear-gradient(135deg, rgba(63,166,107,0.6) 0%, rgba(217,154,61,0.4) 50%, rgba(198,168,120,0.3) 100%)",
        "card-gradient":
          "linear-gradient(160deg, rgba(11,36,26,0.8) 0%, rgba(7,16,13,0.95) 100%)",
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        glow: "0 0 40px rgba(63,166,107,0.15)",
        "glow-amber": "0 0 40px rgba(217,154,61,0.12)",
        "inner-glow": "inset 0 1px 0 rgba(255,255,255,0.04)",
      },
      keyframes: {
        breathe: {
          "0%, 100%": { opacity: "0.92", filter: "drop-shadow(0 0 8px rgba(63,166,107,0.3))" },
          "50%": { opacity: "1", filter: "drop-shadow(0 0 18px rgba(63,166,107,0.5))" },
        },
        floatSlow: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        sweep: {
          "0%": { transform: "translateX(-120%) skewX(-20deg)" },
          "100%": { transform: "translateX(220%) skewX(-20deg)" },
        },
        gradientShift: {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(24px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        drawLine: {
          "0%": { strokeDashoffset: "100%" },
          "100%": { strokeDashoffset: "0%" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        crossfade: {
          "0%": { opacity: "0", transform: "scale(1.06)" },
          "20%, 80%": { opacity: "1", transform: "scale(1)" },
          "100%": { opacity: "0", transform: "scale(1.04)" },
        },
      },
      animation: {
        breathe: "breathe 4.5s ease-in-out infinite",
        floatSlow: "floatSlow 7s ease-in-out infinite",
        sweep: "sweep 9s ease-in-out infinite",
        gradientShift: "gradientShift 8s ease infinite",
        fadeUp: "fadeUp 0.8s cubic-bezier(0.22,1,0.36,1) both",
        pulseSoft: "pulseSoft 3s ease-in-out infinite",
        marquee: "marquee 40s linear infinite",
        crossfade: "crossfade 9s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
