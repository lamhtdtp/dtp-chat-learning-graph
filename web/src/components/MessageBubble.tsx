import { renderRich } from "../markdown";
import type { ChatMessage, Citation, Suggestion } from "../types";
import { VideoBlock } from "./VideoBlock";
import { ItestBlock } from "./ItestBlock";
import { SuggestionChips } from "./SuggestionChips";

// Chip mặc định cho câu trả lời cuối khi thiếu (vd mở lại phiên cũ chưa lưu chip).
const DEFAULT_CHIPS: Suggestion[] = [
  { label: "Tạo một đề ngắn luyện tập", query: "Ôn tập nhanh và ra cho em vài bài tập ngắn phần vừa học" },
];

// "không tìm thấy trong SGK" là trạng thái CỐ Ý (guard chống bịa), phải khác
// biệt trực quan với câu trả lời thường.
function isNotFound(text: string): boolean {
  return text.toLowerCase().includes("không tìm thấy");
}

function citeMap(cites?: Citation[]): Map<number, Citation> {
  const m = new Map<number, Citation>();
  for (const c of cites ?? []) if (!m.has(c.page_no)) m.set(c.page_no, c);
  return m;
}

export function MessageBubble({
  msg, onOpenCitation, showChips = false, onSendChip,
}: {
  msg: ChatMessage;
  onOpenCitation: (c: Citation) => void;
  showChips?: boolean;
  onSendChip?: (q: string) => void;
}) {
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

  const cites = citeMap(msg.citations);
  const hasInline = /\[tr\.\d+\]/.test(msg.text);
  // Chip trích dẫn giờ nằm INLINE ngay trong câu trả lời (marker [tr.N]).
  // Chỉ hiện dải chip ở cuối làm dự phòng khi câu trả lời KHÔNG có marker nào.
  const showBottom = !msg.error && !notFound && !hasInline && (msg.citations?.length ?? 0) > 0;

  return (
    <div className="row bot">
      <div className="bot-stack">
        <div className={cls}>
          {notFound && <div className="notfound-tag">Chưa có trong SGK</div>}
          <div className="bubble-text">
            {msg.error ? msg.text : renderRich(msg.text, cites, onOpenCitation)}
          </div>
          {showBottom && (
            <div className="citations">
              {[...cites.values()].map((c) => {
                const label = `📖 Trang ${c.page_no}${c.bai_so != null ? ` · Bài ${c.bai_so}` : ""}`;
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
          {msg.video && <VideoBlock info={msg.video} />}
          {msg.itest && <ItestBlock offer={msg.itest} />}
        </div>
        {showChips && !msg.error && !notFound && onSendChip &&
          // chips === undefined (phiên cũ) -> dùng mặc định; chips === [] (server
          // bảo KHÔNG mời, vd giải bài tập) -> giữ rỗng, không hiện chip.
          (msg.chips ?? DEFAULT_CHIPS).length > 0 && (
            <SuggestionChips chips={msg.chips ?? DEFAULT_CHIPS} onSend={onSendChip} />
          )}
      </div>
    </div>
  );
}
