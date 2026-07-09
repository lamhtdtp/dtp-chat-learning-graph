import { TOPIC_GROUPS } from "../data";

// Panel phải (desktop): danh mục chủ đề Toán 6, bấm để hỏi nhanh.
export function TopicPanel({ onPick }: { onPick: (q: string) => void }) {
  return (
    <aside className="topic-panel">
      <div className="tp-title">Danh mục Toán lớp 6</div>
      <div className="tp-sub">Chọn một chủ đề để bắt đầu học</div>
      {TOPIC_GROUPS.map((g) => (
        <div key={g.title} className="tp-group">
          <div className="tp-group-title"><span>{g.emoji}</span> {g.title}</div>
          <div className="tp-items">
            {g.items.map((it) => (
              <button key={it} type="button" onClick={() => onPick(`Em muốn học về ${it}`)}>{it}</button>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}
