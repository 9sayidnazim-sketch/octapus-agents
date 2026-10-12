import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  build: {
    outDir: "static",
    emptyOutDir: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/chat": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
