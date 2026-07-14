import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  ApiError, deleteSession, getSessionMessages, getSessions, sendChat, tokenStore,
} from "../api";
import { TUTOR_NAME } from "../config";
import { SUBJECTS, SUBJECT_MAP } from "../subjects";
import { useSpeech } from "../hooks/useSpeech";
import type { ChatMessage, Citation, Role, SessionRow } from "../types";
import { BookPageModal } from "./BookPageModal";
import { MessageBubble } from "./MessageBubble";
import { PracticeExamChip } from "./PracticeExamChip";
import { ChatSidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";
import { TopicPanel } from "./TopicPanel";
import { UserMenu } from "./UserMenu";

export function ChatView({
  initialSubject, name, role, onBackToHub, onOpenExam, onLogout,
}: {
  initialSubject: string;
  name: string;
  role: Role;
  onBackToHub: () => void;
  onOpenExam?: () => void;
  onLogout: () => void;
}) {
  const [subject, setSubject] = useState(initialSubject);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [pageModal, setPageModal] = useState<Citation | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const subj = SUBJECT_MAP[subject] ?? SUBJECTS[0];
  const locked = !subj.unlocked;

  const { supported: micOk, listening, toggle } = useSpeech((t) => setInput(t));

  const refreshSessions = async () => {
    try { setSessions(await getSessions(subject)); } catch { /* bỏ qua */ }
  };
  // Lịch sử theo MÔN: đổi môn -> tải lại danh sách phiên của môn đó.
  useEffect(() => { refreshSessions(); }, [subject]);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handle401 = (err: unknown): boolean => {
    if (err instanceof ApiError && err.status === 401) { tokenStore.clear(); onLogout(); return true; }
    return false;
  };

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy || locked) return;
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    setBusy(true);
    setMessages((m) => [...m, { who: "user", text: q }, { who: "bot", text: "", pending: true }]);
    try {
      const res = await sendChat(q, activeId, subject);
      setActiveId(res.session_id);
      setMessages((m) => [...m.slice(0, -1), {
        who: "bot", text: res.reply, citations: res.citations,
        video: res.video ?? undefined, itest: res.itest ?? undefined, chips: res.suggestions,
      }]);
      refreshSessions();
    } catch (err) {
      if (handle401(err)) return;
      const msg = err instanceof ApiError && err.message ? err.message : "Mình gặp trục trặc khi trả lời, bạn thử lại nhé.";
      setMessages((m) => [...m.slice(0, -1), { who: "bot", text: msg, error: true }]);
    } finally { setBusy(false); }
  };

  const newChat = () => { setActiveId(null); setMessages([]); setDrawer(false); };

  const openSession = async (id: number) => {
    setDrawer(false);
    if (id === activeId) return;
    try {
      const rows = await getSessionMessages(id);
      setActiveId(id);
      setMessages(rows.map((r) => ({
        who: r.role === "assistant" ? "bot" : "user", text: r.content, citations: r.citations ?? undefined,
      })));
    } catch (err) { handle401(err); }
  };

  const removeSession = async (id: number) => {
    try { await deleteSession(id); if (id === activeId) newChat(); refreshSessions(); }
    catch (err) { handle401(err); }
  };

  const autosize = (el: HTMLTextAreaElement) => {
    el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); }
  };

  return (
    <div className="chat-page" data-subject={subject}>
      <div className="app-bar">
        <div className="brand" style={{ cursor: "pointer" }} onClick={onBackToHub} title="Về trang chọn môn">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div className="brand-name">{TUTOR_NAME}</div>
        </div>
        <div className="spacer" />
        {/* GV: nút "Sinh đề" (đề đầy đủ). HS: nút "Đề luyện tập" (đề ngắn theo ma
            trận) — luôn hiện trên header, không phải chờ chip theo ngữ cảnh. */}
        {onOpenExam ? (
          <button className="btn accent hdr-exam-btn" type="button" onClick={onOpenExam} title="Sinh đề kiểm tra theo ma trận">
            📝 Sinh đề
          </button>
        ) : (subj.unlocked && subject === "toan" && (
          <PracticeExamChip label="Đề luyện tập" className="btn accent hdr-exam-btn" icon="📝" />
        ))}
        <ThemeToggle />
        <UserMenu name={name} role={role} onLogout={onLogout} />
      </div>

      {/* Subject switcher — đổi tab là RE-THEME toàn khung chat */}
      <div className="subject-switcher" role="tablist" aria-label="Chọn môn">
        {SUBJECTS.map((s) => (
          <button
            key={s.key}
            role="tab"
            data-subject={s.key}
            aria-current={s.key === subject ? "true" : undefined}
            className={"subject-tab" + (s.unlocked ? "" : " locked")}
            onClick={() => { setSubject(s.key); newChat(); }}
            title={s.unlocked ? s.name : `${s.name} — sắp ra mắt`}
          >
            <span aria-hidden>{s.icon}</span> {s.name}
          </button>
        ))}
      </div>

      <div className={"chat-frame" + (subj.unlocked ? " with-topics" : "")} data-subject={subject}>
        {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}
        <ChatSidebar
          className={drawer ? "open" : ""}
          sessions={sessions} activeId={activeId}
          onSelect={openSession} onDelete={removeSession} onNewChat={newChat}
        />

        <div className="chat-main">
          <div className="chat-head">
            <button className="hamburger" type="button" aria-label="Menu" onClick={() => setDrawer((v) => !v)}>☰</button>
            <div className="subj-ic" aria-hidden>{subj.icon}</div>
            <div>
              <div className="h-name">Gia sư {subj.short}</div>
              <div className="h-sub">Lớp 6</div>
            </div>
            {subj.unlocked && <div className="h-badge">● Bám SGK</div>}
          </div>

          <div className="thread" ref={scrollRef}>
            {locked ? (
              <div className="empty-state">
                <div className="em-ic" aria-hidden>{subj.icon}</div>
                <div className="em-title">Môn {subj.name} sắp ra mắt</div>
                <div>Hiện mới có kho học liệu môn Toán. Chọn Toán để hỏi bài nhé!</div>
              </div>
            ) : messages.length === 0 ? (
              <div className="empty-state">
                <div className="em-ic" aria-hidden>💬</div>
                <div className="em-title">Xin chào! Mình là gia sư {subj.short}</div>
                <div>Chọn một gợi ý bên dưới hoặc gõ câu hỏi để bắt đầu.</div>
              </div>
            ) : (
              messages.map((m, i) => (
                <MessageBubble key={i} msg={m} onOpenCitation={setPageModal}
                  showChips={!busy && i === messages.length - 1} onSendChip={ask} />
              ))
            )}
          </div>

          <div className="chat-foot">
            {/* Gợi ý chỉ hiện khi CHƯA chat (thread rỗng) — chat rồi thì ẩn cho gọn */}
            {!locked && messages.length === 0 && input.trim() === "" && (
              <div className="foot-chips">
                {subj.suggestions.map((s, i) => (
                  <button key={i} className="foot-chip" type="button" onClick={() => ask(s)}>💡 {s}</button>
                ))}
              </div>
            )}
            <div className="composer">
              <textarea
                ref={taRef} value={input} rows={1} disabled={locked} maxLength={200}
                onChange={(e) => { setInput(e.target.value); autosize(e.target); }}
                onKeyDown={onKey}
                placeholder={locked ? "Môn này sắp ra mắt…" : `Hỏi gia sư ${subj.short}…`}
              />
              {micOk && !locked && (
                <button type="button" className={"mic" + (listening ? " on" : "")} onClick={() => toggle(input)} aria-label="Nhập bằng giọng nói">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <rect x="9" y="2" width="6" height="12" rx="3" />
                    <path d="M5 10a7 7 0 0 0 14 0" />
                    <line x1="12" y1="17" x2="12" y2="21" />
                    <line x1="8" y1="21" x2="16" y2="21" />
                  </svg>
                </button>
              )}
              <button type="button" className="send" onClick={() => ask(input)} disabled={busy || locked || !input.trim()} aria-label="Gửi">↑</button>
            </div>
            <div className="foot-note">Trợ lý có thể nhầm — bạn nhớ kiểm tra lại các bước quan trọng nhé.</div>
          </div>
        </div>

        {subj.unlocked && <TopicPanel mon={subj.name} subjectName={subj.short} onPick={ask} />}
      </div>

      {pageModal && <BookPageModal cite={pageModal} mon={subject} onClose={() => setPageModal(null)} />}
    </div>
  );
}
