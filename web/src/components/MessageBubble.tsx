import { renderMath } from "../math";
import type { ChatMessage, Citation } from "../types";

// "không tìm thấy trong SGK" là trạng thái CỐ Ý (guard chống bịa), phải khác
// biệt trực quan với câu trả lời thường — không để học sinh tưởng bot trả lời
// qua loa. Nhận diện theo cụm từ backend trả về.
function isNotFound(text: string): boolean {
  return text.toLowerCase().includes("không tìm thấy");
}

export function MessageBubble({ msg, onOpenCitation }: { msg: ChatMessage; onOpenCitation: (c: Citation) => void }) {
  if (msg.who === "user") {
    return (
      <div className="row user">
        <div className="bubble user">{msg.text}</div>
      </div>
    );
  }

  if (msg.pending) {
    return (
      <div className="row bot">
        <div className="bubble bot pending">
          <span className="dot" /> <span className="dot" /> <span className="dot" />
        </div>
      </div>
    );
  }

  const notFound = !msg.error && isNotFound(msg.text);
  const cls = ["bubble", "bot", msg.error ? "error" : "", notFound ? "notfound" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="row bot">
      <div className={cls}>
        {notFound && <div className="notfound-tag">Chưa có trong SGK</div>}
        <div className="bubble-text">{renderMath(msg.text)}</div>
        {msg.citations && msg.citations.length > 0 && (
          <div className="citations">
            {dedupePages(msg.citations).map((c) => {
              const label = `📖 Trang ${c.page_no}${c.bai_so != null ? ` · Bài ${c.bai_so}` : ""}`;
              // Bấm mở ảnh trang gốc — chỉ khi có `tap` (tin nhắn cũ có thể thiếu).
              return c.tap != null ? (
                <button className="cite-chip clickable" key={c.page_no} onClick={() => onOpenCitation(c)} type="button">
                  {label}
                </button>
              ) : (
                <span className="cite-chip" key={c.page_no}>{label}</span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function dedupePages(cites: ChatMessage["citations"]) {
  const seen = new Set<number>();
  const out: NonNullable<ChatMessage["citations"]> = [];
  for (const c of cites ?? []) {
    if (!seen.has(c.page_no)) {
      seen.add(c.page_no);
      out.push(c);
    }
  }
  return out;
}
