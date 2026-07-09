import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  deleteSession,
  getSessionMessages,
  getSessions,
  sendChat,
  tokenStore,
} from "../api";
import { TUTOR_NAME } from "../config";
import type { ChatMessage, SessionRow } from "../types";
import { MessageBubble } from "./MessageBubble";
import { Sidebar } from "./Sidebar";

const SUGGESTIONS = [
  "Tập hợp là gì?",
  "Cách viết một tập hợp?",
  "Ký hiệu ∈ và ∉ nghĩa là gì?",
];

export function ChatView({ onLogout }: { onLogout: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const refreshSessions = async () => {
    try {
      setSessions(await getSessions());
    } catch {
      /* bỏ qua lỗi tải danh sách */
    }
  };

  useEffect(() => {
    refreshSessions();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handle401 = (err: unknown): boolean => {
    if (err instanceof ApiError && err.status === 401) {
      tokenStore.clear();
      onLogout();
      return true;
    }
    return false;
  };

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { who: "user", text: q }, { who: "bot", text: "", pending: true }]);

    try {
      const res = await sendChat(q, activeId);
      setActiveId(res.session_id);
      setMessages((m) => [...m.slice(0, -1), { who: "bot", text: res.reply, citations: res.citations }]);
      refreshSessions();
    } catch (err) {
      if (handle401(err)) return;
      const msg =
        err instanceof ApiError && err.message
          ? err.message
          : "Mình gặp trục trặc khi trả lời, bạn thử lại nhé.";
      setMessages((m) => [...m.slice(0, -1), { who: "bot", text: msg, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  const newChat = () => {
    setActiveId(null);
    setMessages([]);
    setDrawerOpen(false);
  };

  const openSession = async (id: number) => {
    setDrawerOpen(false);
    if (id === activeId) return;
    try {
      const rows = await getSessionMessages(id);
      setActiveId(id);
      setMessages(
        rows.map((r) => ({
          who: r.role === "assistant" ? "bot" : "user",
          text: r.content,
          citations: r.citations ?? undefined,
        })),
      );
    } catch (err) {
      handle401(err);
    }
  };

  const removeSession = async (id: number) => {
    try {
      await deleteSession(id);
      if (id === activeId) newChat();
      refreshSessions();
    } catch (err) {
      handle401(err);
    }
  };

  return (
    <div className="chat-layout">
      {drawerOpen && <div className="drawer-scrim" onClick={() => setDrawerOpen(false)} />}
      <div className={"sidebar-wrap" + (drawerOpen ? " open" : "")}>
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          onSelect={openSession}
          onDelete={removeSession}
          onNewChat={newChat}
          onLogout={onLogout}
        />
      </div>

      <div className="chat-screen">
        <header className="chat-header">
          <div className="brand">
            <button className="hamburger" onClick={() => setDrawerOpen((v) => !v)} type="button" aria-label="Menu">
              <span /><span /><span />
            </button>
            <div className="avatar"><img src="/dtp-logo.svg" alt="DTP" /></div>
            <div>
              <div className="name">{TUTOR_NAME}</div>
              <div className="online"><span className="dot" /> Đang trực tuyến</div>
            </div>
          </div>
        </header>

        <div className="messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="empty">
              <div className="badge" aria-hidden>🎓</div>
              <p className="empty-title">Xin chào! Mình là {TUTOR_NAME}</p>
              <p>Bạn hỏi mình bất cứ điều gì trong sách Toán nhé. Thử một câu:</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)} type="button">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} />
          ))}
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Hỏi bài hoặc dán đề cần giải…"
            disabled={busy}
          />
          <button className="send" type="submit" disabled={busy || !input.trim()}>Gửi</button>
        </form>
      </div>
    </div>
  );
}
