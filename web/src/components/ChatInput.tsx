import { useRef, type KeyboardEvent } from "react";
import { SUGGESTIONS } from "../data";
import { useSpeech } from "../hooks/useSpeech";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onSendText: (text: string) => void;
  busy?: boolean;
  hasMessages?: boolean;
}

export function ChatInput({ value, onChange, onSend, onSendText, busy, hasMessages }: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const showSuggestions = value.trim() === "" && !hasMessages;
  const { supported: micSupported, listening, toggle } = useSpeech((text) => {
    onChange(text);
    if (taRef.current) autosize(taRef.current);
  });

  const autosize = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
      if (taRef.current) taRef.current.style.height = "auto";
    }
  };

  return (
    <div className="chat-input-wrap">
      <div className="chat-input-inner">
        {showSuggestions && (
          <div className="input-suggests">
            <span className="label">Gợi ý:</span>
            {SUGGESTIONS.map((s, i) => (
              <button key={i} type="button" onClick={() => onSendText(s)}>💡 {s}</button>
            ))}
          </div>
        )}
        <div className="input-box">
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              autosize(e.target);
            }}
            onKeyDown={onKey}
            rows={1}
            placeholder="Hỏi bài, hoặc dán đề cần giải…"
          />
          {micSupported && (
            <button
              type="button"
              className={"mic-btn" + (listening ? " listening" : "")}
              onClick={() => toggle(value)}
              title={listening ? "Đang nghe… bấm để dừng" : "Nói bằng giọng nói"}
              aria-label="Nhập bằng giọng nói"
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect x="9" y="2" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M5 10v1a7 7 0 0 0 14 0v-1" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
                <line x1="12" y1="19" x2="12" y2="22" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
                <line x1="8" y1="22" x2="16" y2="22" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
              </svg>
            </button>
          )}
          <button type="button" className="send-btn" onClick={onSend} disabled={busy || !value.trim()} title="Gửi">
            ↑
          </button>
        </div>
        <div className="input-note">Trợ lý có thể nhầm — bạn nhớ kiểm tra lại các bước quan trọng nhé.</div>
      </div>
    </div>
  );
}
