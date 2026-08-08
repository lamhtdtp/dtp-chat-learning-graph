import { useEffect, useState } from "react";
import { getMe, tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { LearnApp } from "./learn/LearnApp";
import { useTheme } from "./hooks/useTheme";
import type { Role } from "./types";

type Session = { role: Role; name: string } | null;

const CHAN_ADMIN = "Tài khoản quản trị không dùng được ở đây. Bạn vào khu quản trị riêng nhé.";

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
        if (u.role === "admin") { tokenStore.clear(); setSession(null); setChan(CHAN_ADMIN); return; }
        setChan(null);
        setSession({ role: u.role, name: u.name });
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
  return <LearnApp name={session.name} role={session.role} onLogout={handleLogout} />;
}
