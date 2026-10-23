/** @type {import('tailwindcss').Config} */
// Colors are CSS variables (src/index.css) so the light and dark themes share one set of names.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"), // cards and panels
        raised: v("raised"), // wells inside panels
        line: v("line"), // borders and tracks
        ink: v("ink"), // primary text
        muted: v("muted"), // secondary text
        accent: v("accent"), // interactive: buttons, selection, focus
        focus: v("focus"), // amber: the route a request took
        danger: v("danger"),
      },
      fontFamily: {
        sans: ['"Schibsted Grotesk Variable"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgb(var(--shadow) / 0.06), 0 8px 24px -12px rgb(var(--shadow) / 0.18)",
        lift: "0 2px 4px rgb(var(--shadow) / 0.08), 0 16px 32px -12px rgb(var(--shadow) / 0.28)",
      },
    },
  },
  plugins: [],
};
