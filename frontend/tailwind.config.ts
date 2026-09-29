import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b14",
        panel: "rgba(15, 22, 38, 0.78)",
        amber: { glow: "#f5a524" },
        teal: { tech: "#2dd4bf" },
        /* PetroForge brand: earth + green + industrial */
        earth: { 900: "#1a120b", 800: "#2a1d12", 700: "#3d2a18" },
        forest: { 900: "#0d1f16", 800: "#12291d", 700: "#1d3a2a" },
        moss: "#6b8f5e",
        sand: "#d6b98c",
        clay: "#a4713f",
        leaf: "#4ade80",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
