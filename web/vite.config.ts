import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy /auth và /chat sang backend FastAPI (cùng origin trong trình
// duyệt, tránh CORS lúc dev). Production build đọc VITE_API_URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/chat": "http://localhost:8000",
      "/sessions": "http://localhost:8000",
      "/books": "http://localhost:8000",
      "/exam": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
