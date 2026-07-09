import { useEffect, useState } from "react";
import { getMe, tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { ChatView } from "./components/ChatView";
import { ExamView } from "./components/ExamView";
import type { Role } from "./types";

type Session = { role: Role; name: string } | null;

export function App() {
  const [session, setSession] = useState<Session>(null);
  const [ready, setReady] = useState(false);

  const restore = () =>
    getMe()
      .then((u) => setSession({ role: u.role, name: u.name }))
      .catch(() => tokenStore.clear());

  // Reload còn token: hỏi lại /auth/me để khôi phục vai trò (JWT chỉ chứa id).
  useEffect(() => {
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    restore().finally(() => setReady(true));
  }, []);

  const handleLogout = () => {
    tokenStore.clear();
    setSession(null);
  };

  if (!ready) return null;

  if (!session) {
    return <LoginView onAuthed={() => restore()} />;
  }

  return session.role === "giao_vien" ? (
    <ExamView teacherName={session.name} onLogout={handleLogout} />
  ) : (
    <ChatView onLogout={handleLogout} />
  );
}
