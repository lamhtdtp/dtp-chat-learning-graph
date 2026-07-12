import { useEffect, useState } from "react";
import { getTopics } from "../api";
import { TOPIC_GROUPS } from "../data";

// Danh mục chủ đề (cột phải khung chat) — LẤY ĐỘNG từ backend (curriculum_topics),
// gom theo mạch nội dung. Lỗi/rỗng -> fallback danh mục tĩnh (data.ts) để không
// trống. Bấm 1 chủ đề -> gửi vào chat để bắt đầu học.

interface Group { title: string; emoji: string; items: string[] }

// curriculum_topics không có emoji -> gán theo từ khoá mạch nội dung.
function emojiFor(mach: string): string {
  const s = mach.toLowerCase();
  if (s.includes("phân số") || s.includes("thập phân")) return "➗";
  if (s.includes("số nguyên")) return "➖";
  if (s.includes("số tự nhiên") || s.startsWith("số")) return "🔢";
  if (s.includes("thống kê") || s.includes("dữ liệu") || s.includes("xác suất")) return "📊";
  if (s.includes("đối xứng")) return "🔷";
  if (s.includes("hình")) return "📐";
  return "📘";
}

const FALLBACK: Group[] = TOPIC_GROUPS.map((g) => ({ title: g.title, emoji: g.emoji, items: g.items }));

export function TopicPanel({ onPick }: { onPick: (topic: string) => void }) {
  const [groups, setGroups] = useState<Group[] | null>(null);

  useEffect(() => {
    let alive = true;
    getTopics()
      .then((rows) => {
        if (!alive) return;
        const mapped = rows.map((r) => ({ title: r.mach_noi_dung, emoji: emojiFor(r.mach_noi_dung), items: r.items }));
        setGroups(mapped.length ? mapped : FALLBACK);
      })
      .catch(() => alive && setGroups(FALLBACK));
    return () => { alive = false; };
  }, []);

  return (
    <aside className="topic-panel" aria-label="Danh mục chủ đề Toán lớp 6">
      <div className="tp-head">
        <div className="tp-title">Danh mục Toán lớp 6</div>
        <div className="tp-sub">Chọn một chủ đề để bắt đầu học</div>
      </div>
      <div className="tp-scroll">
        {groups === null ? (
          <div className="tp-loading">Đang tải danh mục…</div>
        ) : (
          groups.map((g) => (
            <div className="tp-group" key={g.title}>
              <div className="tp-group-title">
                <span aria-hidden>{g.emoji}</span> {g.title.toUpperCase()}
              </div>
              <div className="tp-items">
                {g.items.map((it) => (
                  <button key={it} type="button" className="tp-chip" onClick={() => onPick(it)}>
                    {it}
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
