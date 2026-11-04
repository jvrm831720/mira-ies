import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "var(--color-page-canvas)",
        ink: "var(--color-ink-black)",
        graphite: "var(--color-graphite)",
        carbon: "var(--color-carbon)",
        slate: {
          500: "var(--color-slate-500)",
          600: "var(--color-slate-600)",
          700: "var(--color-slate-700)",
        },
        fog: "var(--color-fog-400)",
        mist: {
          50: "var(--color-mist-50)",
          300: "var(--color-mist-300)",
        },
        cloud: {
          100: "var(--color-cloud-100)",
          200: "var(--color-cloud-200)",
        },
        haze: "var(--color-haze)",
        paper: "var(--color-paper)",
        periwinkle: "var(--color-periwinkle)",
        cobalt: {
          DEFAULT: "var(--color-cobalt-core)",
          bright: "var(--color-cobalt-bright)",
          soft: "var(--color-cobalt-soft)",
        },
        ice: "var(--color-ice-wash)",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius-control)",
        md: "8px",
        sm: "7px",
        card: "var(--radius-card)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-interdisplay)", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "var(--shadow-card)",
        subtle: "var(--shadow-subtle)",
        elevated: "var(--shadow-overlay)",
      },
    },
  },
  plugins: [],
};

export default config;
