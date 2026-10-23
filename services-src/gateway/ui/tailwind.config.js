/** @type {import('tailwindcss').Config} */
// Colors are CSS variables (src/index.css) so the light and dark themes share one set of names.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        table: v("table"), // the light-table background
        sheet: v("sheet"), // surfaces images sit on
        frame: v("frame"), // primary text and strong lines
        graphite: v("graphite"), // secondary text
        rule: v("rule"), // hairlines and tracks
        marker: v("marker"), // grease-pencil amber: the route a request took
        "marker-ink": v("marker-ink"), // text on marker
        alert: v("alert"),
      },
      fontFamily: {
        sans: ['"Schibsted Grotesk Variable"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
