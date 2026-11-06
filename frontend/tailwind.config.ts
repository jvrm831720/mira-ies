import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "var(--color-border)",
        input: "var(--color-border)",
        ring: "var(--color-blue)",
        background: "var(--color-canvas)",
        foreground: "var(--color-ink)",
        primary: { DEFAULT: "var(--color-ink)", foreground: "var(--color-canvas)" },
        secondary: { DEFAULT: "var(--color-panel)", foreground: "var(--color-ink)" },
        muted: { DEFAULT: "var(--color-panel)", foreground: "var(--color-slate-600)" },
        accent: { DEFAULT: "var(--color-blue-tint)", foreground: "var(--color-blue)" },
        destructive: { DEFAULT: "var(--color-red)", foreground: "var(--color-canvas)" },
        card: { DEFAULT: "var(--color-canvas)", foreground: "var(--color-ink)" },
        success: { DEFAULT: "var(--color-green)", foreground: "var(--color-canvas)" },
        warning: { DEFAULT: "var(--color-peach-tint)", foreground: "var(--color-ink)" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
