import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// App QUẢN TRỊ độc lập (container web-admin riêng). 1 trang duy nhất (index.html
// -> src/admin/main.tsx). Dev proxy các API cần cho quản trị sang FastAPI :8000.
// Production build đọc VITE_API_URL (URL backend mà TRÌNH DUYỆT gọi).
export default defineConfig({
  plugins: [react()],
  // Base path cho triển khai dưới subpath cùng domain (vd /quan-tri/). Mặc định "/"
  // (chạy ở gốc, tiện dev). Prod 1-domain: build với ADMIN_BASE=/quan-tri/.
  base: process.env.ADMIN_BASE || "/",
  server: {
    port: 5174,
    proxy: {
      "/auth": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/cms": "http://localhost:8000",         // CMS chuyên gia biên soạn giáo trình
      "/video": "http://localhost:8000",       // upload/thay video minh họa
      // Xem thử phạm vi ôn tập dùng CHUNG endpoint với app học sinh (/on-tap),
      // không nằm dưới /cms — thiếu dòng này thì dev server trả index.html và
      // client báo "không tải được" mà không có lỗi HTTP nào để lần.
      "/on-tap": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
