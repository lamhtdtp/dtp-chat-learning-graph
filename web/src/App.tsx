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
  // null = đang ở Subject Hub; có key = đang chat môn đó.
  const [subject, setSubject] = useState<string | null>(null);
  // Giáo viên: mở màn Sinh đề (theo ma trận). Học sinh không dùng.
  const [showExam, setShowExam] = useState(false);

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
    setShowExam(false);
  };

  if (!ready) return null;
  if (!session) return <LoginView onAuthed={() => restore()} />;

  const isTeacher = session.role === "giao_vien";

  // Giáo viên: màn Sinh đề (Toán, theo ma trận) — mở từ Hub, có nút quay lại.
  if (showExam && isTeacher) {
    return <ExamView teacherName={session.name} onBack={() => setShowExam(false)} onLogout={handleLogout} />;
  }

  // Cả học sinh & giáo viên đều qua Subject Hub -> Chat (đa môn, gồm Tiếng Anh).
  if (subject == null) {
    return (
      <SubjectHub
        name={session.name}
        role={session.role}
        onOpenSubject={(key) => setSubject(key)}
        onOpenExam={isTeacher ? () => setShowExam(true) : undefined}
        onLogout={handleLogout}
      />
    );
  }
  return (
    <ChatView
      initialSubject={subject || DEFAULT_SUBJECT}
      name={session.name}
      role={session.role}
      onBackToHub={() => setSubject(null)}
      onLogout={handleLogout}
    />
  );
}
