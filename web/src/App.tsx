import { useEffect, useState } from "react";
import { getMe, tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { LearnApp } from "./learn/LearnApp";
import { useTheme } from "./hooks/useTheme";
import type { Role } from "./types";

type Session = { role: Role; name: string } | null;

export function App() {
  useTheme(); // áp data-theme (auto/light/dark) lên <html> ngay từ đầu
  const [session, setSession] = useState<Session>(null);
  const [ready, setReady] = useState(false);

  const restore = () =>
    getMe()
      .then((u) => setSession({ role: u.role, name: u.name }))
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
  if (!session) return <LoginView onAuthed={() => restore()} />;

  // Quản trị viên dùng KHU RIÊNG tại /admin (app tách riêng) — không vào app này.
  // Học sinh & giáo viên: nền tảng giáo trình có cấu trúc (Mục lục → Bài học 4
  // phần → Tiến độ / Slide). Không còn chat/RAG (đã bỏ theo mockup).
  return <LearnApp name={session.name} role={session.role} onLogout={handleLogout} />;
}
