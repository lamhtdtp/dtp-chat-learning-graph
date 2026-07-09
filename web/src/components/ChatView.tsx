import { useEffect, useRef, useState } from "react";
import { ApiError, sendChat, tokenStore } from "../api";
import { APP_NAME, TUTOR_NAME } from "../config";
import type { ChatMessage } from "../types";
import { MessageBubble } from "./MessageBubble";

const SUGGESTIONS = [
  "Tập hợp là gì?",
  "Cách viết một tập hợp?",
  "Ký hiệu ∈ và ∉ nghĩa là gì?",
];

// 1 phiên chat cố định cho MVP; thread_id phía backend đã gồm user_id nên các
// user không lẫn nhau. Nhiều phiên/lịch sử để sau.
const SESSION_ID = "default";

export function ChatView({ onLogout }: { onLogout: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { who: "user", text: q }, { who: "bot", text: "", pending: true }]);

    try {
      const res = await sendChat(q, SESSION_ID);
      setMessages((m) => [
        ...m.slice(0, -1),
        { who: "bot", text: res.reply, citations: res.citations },
      ]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        tokenStore.clear();
        onLogout();
        return;
      }
      setMessages((m) => [
        ...m.slice(0, -1),
        { who: "bot", text: "Mình gặp trục trặc khi trả lời, bé thử lại nhé.", error: true },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-screen">
      <header className="chat-header">
        <div className="header-brand">
          <img className="header-logo" src="/dtp-logo.svg" alt="DTP" />
          <div>
            <strong>{TUTOR_NAME}</strong>
            <span className="header-sub">{APP_NAME}</span>
          </div>
        </div>
        <button className="logout" onClick={onLogout} type="button">Đăng xuất</button>
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty">
            <p className="empty-title">Xin chào! Mình là {TUTOR_NAME} 🎓</p>
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
        <button className="send" type="submit" disabled={busy || !input.trim()}>
          Gửi
        </button>
      </form>
    </div>
  );
}
