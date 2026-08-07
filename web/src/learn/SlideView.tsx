import { useEffect, useMemo, useState } from "react";
import type { Lesson } from "../types";

type Slide =
  | { kicker: string; h: string; cover?: boolean; body?: string }
  | { kicker: string; h: string; html: string }
  | { kicker: string; h: string; caption: string }
  | { kicker: string; h: string; list: string[] };

function buildSlides(L: Lesson): Slide[] {
  const s: Slide[] = [
    { cover: true, kicker: L.mach, h: L.dv, body: "Bài giảng tạo tự động từ nội dung đã nhập · Gia sư DTP" },
    { kicker: "Khái niệm", h: "Khái niệm & định nghĩa", html: L.khai_niem || "(chưa có)" },
  ];
  L.minh_hoa.forEach((m, i) => s.push({ kicker: "Minh hoạ", h: `Minh hoạ ${i + 1}`, caption: m.caption || "(media)" }));
  if (L.vi_du.length) s.push({ kicker: "Ví dụ", h: "Ví dụ minh hoạ", list: L.vi_du.map((e) => e.de) });
  return s;
}

export function SlideView({ lesson }: { lesson: Lesson }) {
  const slides = useMemo(() => buildSlides(lesson), [lesson]);
  const [idx, setIdx] = useState(0);
  useEffect(() => { setIdx(0); }, [lesson]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setIdx((i) => Math.min(slides.length - 1, i + 1));
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [slides.length]);

  const s = slides[idx] as Slide & Record<string, unknown>;
  return (
    <div className="lesson">
      <span className="eyebrow">🖥️ Slide giảng dạy · {slides.length} slide</span>
      <h1 style={{ marginBottom: 16 }}>{lesson.dv}</h1>

      <div className="deck">
        <div className={"slide" + ((s as {cover?: boolean}).cover ? " cover" : "")}>
          <div className="kicker">{s.kicker}</div>
          <h2>{s.h}</h2>
          {"body" in s && s.body ? <div className="body">{s.body as string}</div> : null}
          {"html" in s && <div className="body" dangerouslySetInnerHTML={{ __html: s.html as string }} />}
          {"caption" in s && <div className="body">{s.caption as string}</div>}
          {"list" in s && <ul>{(s.list as string[]).map((x, i) => <li key={i} dangerouslySetInnerHTML={{ __html: x }} />)}</ul>}
        </div>
        <div className="deck-bar">
          <button className="btn" type="button" disabled={idx === 0} onClick={() => setIdx((i) => i - 1)}>‹ Trước</button>
          <button className="btn btn-primary" type="button" disabled={idx === slides.length - 1} onClick={() => setIdx((i) => i + 1)}>Sau ›</button>
          <div className="count">Slide {idx + 1}/{slides.length}</div>
          <div className="dots">{slides.map((_, i) => <i key={i} className={i === idx ? "on" : ""} />)}</div>
        </div>
      </div>
    </div>
  );
}
