import { useEffect, useRef, useState } from "react";
import { ApiError, askTutor, getTutorLimits, tokenStore } from "../api";
import { renderMath } from "../mathHtml";

type Msg = { role: "me" | "bot"; html: string; error?: boolean };

// Dùng khi GET /tutor/limits lỗi. Giữ khớp mặc định settings.chat_max_chars.
const FALLBACK_MAX_CHARS = 500;
// Từ mốc này mới hiện bộ đếm — hiện suốt thì thành tiếng ồn cho câu hỏi ngắn.
const HIEN_DEM_TU = 0.7;

// Chuẩn hoá câu trả lời trợ lý -> HTML: render công thức LaTeX ($…$, $$…$$) bằng
// KaTeX (không còn hiện ký tự $ — dùng chung renderMath với trang bài học), bỏ
// trích trang sách [tr.N], markdown nhẹ.
function toHtml(answer: string): string {
  return renderMath(answer.replace(/\s*\[tr\.?\s*\d+\s*\]/gi, ""))   // bỏ suggest trang sách [tr.45]
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/(^|\n)\s*[*•-]\s+/g, "$1• ")
    .replace(/\s+([.,;!?])/g, "$1")                   // dọn khoảng trắng thừa trước dấu câu
    .replace(/\n{2,}/g, "<br><br>")
    .replace(/\n/g, "<br>");
}

/** Trợ lý hỏi–đáp bám SGK (cột phải). Stateless mỗi lượt (không lưu hội thoại ở
 *  server). `injected` cho phép chip gợi ý bên bài học đẩy câu hỏi sang. */
export function ChatPanel({ lessonName, injected, onLogout }: {
  lessonName: string | null;
  injected: { q: string; n: number } | null;
  onLogout: () => void;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  // Giới hạn ký tự lấy từ server (settings.chat_max_chars). Fallback bằng
  // FALLBACK_MAX_CHARS nếu gọi lỗi: thà chặn theo con số cũ hơn là để ô nhập
  // không giới hạn rồi HS mất một vòng request mới biết mình viết quá dài.
  const [maxChars, setMaxChars] = useState(FALLBACK_MAX_CHARS);
  const logRef = useRef<HTMLDivElement>(null);

  const greeting = lessonName
    ? `Chào bạn 👋 Hỏi mình bất cứ điều gì về bài <b>${lessonName}</b> — mình trả lời bám sách giáo khoa.`
    : "Chào bạn 👋 Chọn một bài học rồi hỏi mình nhé — mình trả lời bám sách giáo khoa.";

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs, sending]);

  useEffect(() => {
    getTutorLimits().then((l) => setMaxChars(l.max_chars)).catch(() => { /* giữ fallback */ });
  }, []);

  const ask = async (raw: string) => {
    const q = raw.trim();
    if (!q || sending) return;
    // Chặn ở client cho MỌI đường vào (ô nhập lẫn chip gợi ý đẩy sang) — không
    // để 400 của server là nơi HS đầu tiên biết mình viết quá dài. Giữ nguyên
    // câu trong ô để HS cắt bớt, không xoá công của họ.
    if (q.length > maxChars) {
      setMsgs((m) => [...m, { role: "bot", error: true, html:
        `⚠️ Câu hỏi dài ${q.length} ký tự, tối đa ${maxChars}. Bạn rút ngắn lại giúp mình nhé — hỏi từng ý một sẽ dễ trả lời hơn.` }]);
      return;
    }
    setInput("");
    setMsgs((m) => [...m, { role: "me", html: q }]);
    setSending(true);
    try {
      const a = await askTutor(q, "Toán", lessonName ?? undefined);
      setMsgs((m) => [...m, { role: "bot", html: toHtml(a.answer) }]);
      setRemaining(a.remaining);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return; }
      const msg = e instanceof ApiError ? e.message : "Không kết nối được máy chủ";
      setMsgs((m) => [...m, { role: "bot", html: "⚠️ " + msg, error: true }]);
    } finally {
      setSending(false);
    }
  };

  // Chip gợi ý bên bài học đẩy câu hỏi sang (đổi nonce -> hỏi).
  useEffect(() => { if (injected?.q) ask(injected.q); /* eslint-disable-next-line */ }, [injected?.n]);

  return (
    <aside className="chat col">
      <div className="chat-head">
        <div className="chat-ava">
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>
        </div>
        <div><b>Trợ lý học Toán</b><div className="on">Trả lời bám sách giáo khoa</div></div>
      </div>

      <div className="chat-log" ref={logRef}>
        <div className="msg bot"><div className="bubble" dangerouslySetInnerHTML={{ __html: greeting }} /></div>
        {msgs.map((m, i) => (
          <div className={"msg " + m.role} key={i}>
            <div className="bubble" dangerouslySetInnerHTML={{ __html: m.html }} />
          </div>
        ))}
        {sending && (
          <div className="msg bot"><div className="bubble"><div className="typing"><i /><i /><i /></div></div></div>
        )}
      </div>

      {remaining != null && <div className="chat-quota">Còn {remaining} lượt hỏi hôm nay</div>}
      <div className="chat-in">
        {/* maxLength chặn gõ/dán vượt hạn; bộ đếm cho HS thấy còn bao nhiêu chỗ
            TRƯỚC khi gửi, chỉ hiện khi đã dùng phần lớn hạn mức. */}
        <textarea rows={1} value={input} placeholder="Nhập câu hỏi về bài học…" maxLength={maxChars}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); } }} />
        {input.length >= maxChars * HIEN_DEM_TU && (
          <span className={"chat-dem" + (input.length >= maxChars ? " het" : "")}
            aria-live="polite">{input.length}/{maxChars}</span>
        )}
        <button className="send" type="button" disabled={sending || !input.trim()} onClick={() => ask(input)} aria-label="Gửi">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
        </button>
      </div>
    </aside>
  );
}
