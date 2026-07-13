import { useEffect, useState } from "react";
import { getTopics } from "../api";
import { TOPIC_GROUPS } from "../data";

// Danh mục chủ đề (cột phải khung chat) — LẤY ĐỘNG từ backend (curriculum_topics),
// gom theo mạch nội dung. Lỗi/rỗng -> fallback danh mục tĩnh (data.ts) để không
// trống. Bấm 1 chủ đề -> gửi vào chat để bắt đầu học.

interface Item { ten: string; co_video: boolean }
interface Group { title: string; emoji: string; items: Item[] }

// curriculum_topics không có emoji -> gán theo từ khoá mạch nội dung (đa môn).
function emojiFor(mach: string): string {
  const s = mach.toLowerCase();
  if (s.includes("phân số") || s.includes("thập phân")) return "➗";
  if (s.includes("số nguyên")) return "➖";
  if (s.includes("số tự nhiên") || s.startsWith("số")) return "🔢";
  if (s.includes("thống kê") || s.includes("dữ liệu") || s.includes("xác suất")) return "📊";
  if (s.includes("đối xứng")) return "🔷";
  if (s.includes("hình")) return "📐";
  // Tiếng Anh
  if (s.includes("grammar") || s.includes("ngữ pháp")) return "📝";
  if (s.includes("vocab") || s.includes("từ vựng")) return "🔤";
  if (s.includes("read") || s.includes("đọc")) return "📖";
  if (s.includes("listen") || s.includes("nghe")) return "🎧";
  if (s.includes("speak") || s.includes("nói") || s.includes("phát âm")) return "🗣️";
  if (s.includes("writ") || s.includes("viết")) return "✍️";
  return "📘";
}

// Fallback tĩnh CHỈ dùng cho Toán (data.ts là danh mục Toán). Môn khác không có
// fallback tĩnh -> rỗng thì báo "chưa có" thay vì hiện nhầm danh mục Toán.
const MATH_FALLBACK: Group[] = TOPIC_GROUPS.map((g) => ({
  title: g.title, emoji: g.emoji, items: g.items.map((ten) => ({ ten, co_video: false })),
}));

export function TopicPanel({ mon, subjectName, onPick }: { mon: string; subjectName: string; onPick: (topic: string) => void }) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const fallback = mon === "Toán" ? MATH_FALLBACK : [];

  useEffect(() => {
    let alive = true;
    setGroups(null);
    getTopics(mon)
      .then((rows) => {
        if (!alive) return;
        const mapped = rows.map((r) => ({ title: r.mach_noi_dung, emoji: emojiFor(r.mach_noi_dung), items: r.items }));
        // backend đã sắp item/nhóm có video lên đầu; giữ nguyên thứ tự đó.
        setGroups(mapped.length ? mapped : fallback);
      })
      .catch(() => alive && setGroups(fallback));
    return () => { alive = false; };
  }, [mon]);

  return (
    <aside className="topic-panel" aria-label={`Danh mục chủ đề ${subjectName} lớp 6`}>
      <div className="tp-head">
        <div className="tp-title">Danh mục {subjectName} lớp 6</div>
        <div className="tp-sub">Chọn một chủ đề để bắt đầu học</div>
      </div>
      <div className="tp-scroll">
        {groups === null ? (
          <div className="tp-loading">Đang tải danh mục…</div>
        ) : groups.length === 0 ? (
          <div className="tp-loading">Chưa có danh mục cho môn này.</div>
        ) : (
          groups.map((g) => (
            <div className="tp-group" key={g.title}>
              <div className="tp-group-title">
                <span aria-hidden>{g.emoji}</span> {g.title.toUpperCase()}
              </div>
              <div className="tp-items">
                {g.items.map((it) => (
                  <button key={it.ten} type="button" className={"tp-chip" + (it.co_video ? " has-video" : "")}
                    onClick={() => onPick(it.ten)} title={it.co_video ? "Có video minh hoạ" : undefined}>
                    {it.co_video && <span className="tp-chip-vid" aria-label="Có video">▶</span>}
                    {it.ten}
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
