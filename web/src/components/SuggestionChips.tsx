import type { Suggestion } from "../types";
import { PracticeExamChip } from "./PracticeExamChip";

// Chip gợi ý dưới câu trả lời (viền xanh + mũi tên cam), port từ dtp-chat-learning.
// action="practice_exam" -> nút mở đề ngắn theo ma trận; còn lại -> gửi query chat.
export function SuggestionChips({ chips, onSend }: { chips: Suggestion[]; onSend: (q: string) => void }) {
  if (!chips.length) return null;
  return (
    <div className="chips">
      {chips.map((c, i) =>
        c.action === "practice_exam" ? (
          <PracticeExamChip key={i} label={c.label} />
        ) : (
          <button key={i} className="chip" type="button" onClick={() => onSend(c.query || c.label)}>
            <span className="chip-arrow">→</span> {c.label}
          </button>
        ),
      )}
    </div>
  );
}
