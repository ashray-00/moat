import type { Config } from "tailwindcss";

/**
 * Moat design tokens (Tailwind v4 also maps these in app/globals.css via @theme).
 *
 * Palette — restrained fintech / editorial:
 *   canvas  #FAFAF8  warm off-white surface
 *   ink     #141816  near-black body text
 *   mist    #6B6A64  secondary / muted
 *   stone   #9C9A92  tertiary
 *   line    #E5E3DB  hairline borders
 *   accent  #1F4E3D  deep ledger green (not Tailwind blue)
 *
 * Type —
 *   display: Newsreader (editorial serif)
 *   sans:    Geist (UI / body)
 *   mono:    IBM Plex Mono (citation ids)
 */
const config = {
  theme: {
    extend: {
      colors: {
        canvas: "var(--moat-canvas)",
        surface: "var(--moat-surface)",
        ink: "var(--moat-ink)",
        mist: "var(--moat-mist)",
        stone: "var(--moat-stone)",
        line: "var(--moat-line)",
        accent: "var(--moat-accent)",
        "accent-hover": "var(--moat-accent-hover)",
        "accent-muted": "var(--moat-accent-muted)",
      },
      fontFamily: {
        display: ["var(--font-newsreader)", "Georgia", "serif"],
        sans: ["var(--font-geist)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
      },
      maxWidth: {
        measure: "44rem", // ~704px — between 640–720
      },
      boxShadow: {
        search: "var(--moat-shadow-search)",
        chip: "var(--moat-shadow-chip)",
      },
      borderRadius: {
        search: "0.625rem",
        chip: "0.375rem",
      },
    },
  },
} satisfies Config;

export default config;
