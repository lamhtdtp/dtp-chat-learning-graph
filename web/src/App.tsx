import { useEffect, useState } from "react";
import { getMe, tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { LearnApp } from "./learn/LearnApp";
import { useTheme } from "./hooks/useTheme";
import type { Role } from "./types";

// email lấy luôn từ /auth/me của restore() — MỌI lối vào (đăng nhập mới lẫn
// khôi phục token) đều đi qua đó, nên hồ sơ không cần gọi lại lần nữa.
type Session = { role: Role; name: string; email: string } | null;

// Vai trò CMS-only: không có gì để học ở app này.
const CHI_CMS: Role[] = ["chuyen_gia", "admin"];
const CHAN_CMS = "Tài khoản quản trị / chuyên gia không dùng được ở đây. Bạn vào khu quản trị riêng nhé.";

export function App() {
  useTheme(); // áp data-theme (auto/light/dark) lên <html> ngay từ đầu
  const [session, setSession] = useState<Session>(null);
  const [ready, setReady] = useState(false);
  const [chan, setChan] = useState<string | null>(null);

  // Chặn ở ĐÂY chứ không phải trong LoginView: đường vào có hai lối — đăng nhập
  // mới, và khôi phục phiên cũ từ token còn trong localStorage. Đặt ở LoginView
  // thì lối thứ hai lọt.
  const restore = () =>
    getMe()
      .then((u) => {
        if (CHI_CMS.includes(u.role)) { tokenStore.clear(); setSession(null); setChan(CHAN_CMS); return; }
        setChan(null);
        setSession({ role: u.role, name: u.name, email: u.email });
      })
      .catch(() => tokenStore.clear());

  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return; }
    restore().finally(() => setReady(true));
  }, []);

  const handleLogout = () => {
    tokenStore.clear();
    setSession(null);
  };

  if (!ready) return null;
  // Quản trị viên dùng KHU RIÊNG (app web-admin) — token đã bị xoá ở restore(),
  // `chan` chỉ để nói cho họ biết vì sao bị đẩy về trang đăng nhập.
  if (!session) return <LoginView onAuthed={() => restore()} chanDangNhap={chan} />;

  // Học sinh & giáo viên: nền tảng giáo trình có cấu trúc (Mục lục → Bài học 4
  // phần → Tiến độ / Slide).
  return <LearnApp name={session.name} email={session.email} role={session.role} onLogout={handleLogout} />;
}
