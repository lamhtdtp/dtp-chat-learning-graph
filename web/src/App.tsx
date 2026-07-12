import { useEffect, useState } from "react";
import { getMe, tokenStore } from "./api";
import { LoginView } from "./components/LoginView";
import { ChatView } from "./components/ChatView";
import { ExamView } from "./components/ExamView";
import { SubjectHub } from "./components/SubjectHub";
import { useTheme } from "./hooks/useTheme";
import { DEFAULT_SUBJECT } from "./subjects";
import type { Role } from "./types";

type Session = { role: Role; name: string } | null;

export function App() {
  useTheme(); // áp data-theme (auto/light/dark) lên <html> ngay từ đầu
  const [session, setSession] = useState<Session>(null);
  const [ready, setReady] = useState(false);
  // Học sinh: null = đang ở Subject Hub; có key = đang chat môn đó.
  const [subject, setSubject] = useState<string | null>(null);

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
    setSubject(null);
  };

  if (!ready) return null;
  if (!session) return <LoginView onAuthed={() => restore()} />;

  if (session.role === "giao_vien") {
    return <ExamView teacherName={session.name} onLogout={handleLogout} />;
  }

  // Học sinh: Subject Hub -> Chat (một môn).
  if (subject == null) {
    return (
      <SubjectHub
        name={session.name}
        onOpenSubject={(key) => setSubject(key)}
        onLogout={handleLogout}
      />
    );
  }
  return (
    <ChatView
      initialSubject={subject || DEFAULT_SUBJECT}
      name={session.name}
      onBackToHub={() => setSubject(null)}
      onLogout={handleLogout}
    />
  );
}
