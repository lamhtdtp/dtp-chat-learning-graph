import type { Suggestion } from "../types";

// Chip gợi ý bước tiếp theo, đặt ngay dưới câu trả lời (viền xanh + mũi tên cam),
// port từ repo dtp-chat-learning. Bấm -> gửi query như tin nhắn mới.
export function SuggestionChips({ chips, onSend }: { chips: Suggestion[]; onSend: (q: string) => void }) {
  if (!chips.length) return null;
  return (
    <div className="chips">
      {chips.map((c, i) => (
        <button key={i} className="chip" type="button" onClick={() => onSend(c.query || c.label)}>
          <span className="chip-arrow">→</span> {c.label}
        </button>
      ))}
    </div>
  );
}
