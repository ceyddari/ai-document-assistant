import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // strictPort: the API's CORS list only allows 5173, so fail loudly instead of moving to 5174.
  server: { port: 5173, strictPort: true },
});
