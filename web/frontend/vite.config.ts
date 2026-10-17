import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El backend FastAPI corre en :8000 (o en API_PORT); el proxy evita CORS en desarrollo.
declare const process: { env: Record<string, string | undefined> };
const api = `http://localhost:${process.env.API_PORT || 8000}`;
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/ws": { target: api, ws: true },
    },
  },
});
