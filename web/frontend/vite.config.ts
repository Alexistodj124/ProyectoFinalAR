import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// El backend FastAPI corre en :8000; el proxy evita CORS en desarrollo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "http://localhost:8000", ws: true },
    },
  },
});
