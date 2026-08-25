import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy các route API sang backend FastAPI (cùng origin trong trình duyệt,
// tránh CORS lúc dev). Production build đọc VITE_API_URL.
// App học sinh/giáo viên — nền tảng giáo trình (chat/RAG/sinh-đề đã bỏ ở P5).
// Khu QUẢN TRỊ tách sang container riêng (web-admin).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/video": "http://localhost:8000",       // phát video minh họa (đã ký URL)
      // Giáo trình có cấu trúc: mục lục, bài học 4 phần, tiến độ, kiểm tra nhanh.
      "/curriculum": "http://localhost:8000",
      "/lessons": "http://localhost:8000",
      "/progress": "http://localhost:8000",
      "/quiz": "http://localhost:8000",
      "/me": "http://localhost:8000",           // hero gamification (XP/streak/tiến độ)
      "/tutor": "http://localhost:8000",        // trợ lý hỏi–đáp bám SGK
      // Ôn tập chương / cuối kỳ (§3.5). Thiếu dòng này thì trang ôn tập nhận về
      // index.html của Vite chứ không phải JSON, và lỗi hiện ra là "không tải
      // được" mà không có mã HTTP nào để lần — đã mất một lần ở web-admin.
      "/on-tap": "http://localhost:8000",
    },
  },
});
