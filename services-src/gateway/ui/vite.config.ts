import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the UI on :5173 and forwards API calls to a running gateway,
// e.g. GATEWAY_URL=http://127.0.0.1:39297 npm run dev (the `minikube service --url` tunnel).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.GATEWAY_URL ?? "http://127.0.0.1:8080" },
  },
});
