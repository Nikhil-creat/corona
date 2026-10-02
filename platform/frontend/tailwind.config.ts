import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { void: "#05070d", panel: "#0b1020", edge: "#1b2744", neon: "#38bdf8", amber2: "#fbbf24", ok: "#34d399", danger: "#f87171" },
      fontFamily: { mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
};
export default config;
