import { useMemo, useState } from "react";
import { renderRich } from "../markdown";
import type { LessonContent, LessonQuickCheck } from "../types";
import { Portal } from "./Portal";

// Bài học 1 Đơn vị kiến thức — 4 phần THEO THỨ TỰ CỐ ĐỊNH (meeting note), KHÔNG
// trích dẫn số trang. Hiện là bản dựng UX (data giả); sau nối GET /lessons.
const NO_CITE = new Map();
const rich = (s: string) => renderRich(s, NO_CITE, () => {});

const SECTIONS = [
  { n: 1, key: "khai_niem", title: "Khái niệm, định nghĩa", icon: "📖" },
  { n: 2, key: "minh_hoa", title: "Minh họa", icon: "🎬" },
  { n: 3, key: "vi_du", title: "Ví dụ", icon: "✏️" },
  { n: 4, key: "kiem_tra", title: "Bài kiểm tra nhanh", icon: "✅" },
] as const;

export function LessonView({ content, onBack }: { content: LessonContent; onBack: () => void }) {
  return (
    <Portal>
      <div className="lesson-page" data-subject="toan">
        <div className="app-bar">
          <button className="btn" type="button" onClick={onBack}>← Mục lục</button>
          <div className="lesson-crumb">
            <span className="lesson-mach">{content.mach_noi_dung}</span>
            <span className="lesson-dv">{content.don_vi_kien_thuc}</span>
          </div>
          <div className="spacer" />
        </div>

        <div className="lesson-scroll">
          <div className="lesson-wrap">
            {/* 1. Khái niệm */}
            <Section n={1}>
              <div className="bubble-text">{rich(content.khai_niem)}</div>
            </Section>

            {/* 2. Minh họa */}
            <Section n={2}>
              <div className="lesson-media">
                {content.minh_hoa.map((m, i) => (
                  <figure className="lesson-media-item" key={i}>
                    {m.loai === "image" ? (
                      m.url
                        ? <img src={m.url} alt={m.caption || ""} />
                        : <div className="lesson-media-ph">🖼️ Hình ảnh</div>
                    ) : (
                      m.url
                        ? <video src={m.url} controls preload="metadata" />
                        : <div className="lesson-media-ph">▶ Video minh hoạ</div>
                    )}
                    {m.caption && <figcaption>{m.caption}</figcaption>}
                  </figure>
                ))}
                {content.minh_hoa.length === 0 && <div className="lesson-empty">Chưa có minh hoạ.</div>}
              </div>
            </Section>

            {/* 3. Ví dụ */}
            <Section n={3}>
              {content.vi_du.map((v, i) => <Example key={i} idx={i} deBai={v.de_bai} loiGiai={v.loi_giai} />)}
              {content.vi_du.length === 0 && <div className="lesson-empty">Chưa có ví dụ.</div>}
            </Section>

            {/* 4. Bài kiểm tra nhanh */}
            <Section n={4}>
              <QuickCheck items={content.kiem_tra_nhanh} />
            </Section>
          </div>
        </div>
      </div>
    </Portal>
  );
}

function Section({ n, children }: { n: number; children: React.ReactNode }) {
  const s = SECTIONS.find((x) => x.n === n)!;
  return (
    <section className="lesson-sec">
      <div className="lesson-sec-h">
        <span className="lesson-sec-n" aria-hidden>{s.n}</span>
        <span aria-hidden>{s.icon}</span> {s.title}
      </div>
      <div className="lesson-sec-body">{children}</div>
    </section>
  );
}

function Example({ idx, deBai, loiGiai }: { idx: number; deBai: string; loiGiai: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="lesson-vd">
      <div className="lesson-vd-h">Ví dụ {idx + 1}</div>
      <div className="bubble-text">{rich(deBai)}</div>
      <button className="exam-q-toggle" type="button" onClick={() => setOpen((v) => !v)}>
        {open ? "Ẩn lời giải" : "Xem lời giải"}
      </button>
      {open && <div className="lesson-vd-giai bubble-text">{rich(loiGiai)}</div>}
    </div>
  );
}

function QuickCheck({ items }: { items: LessonQuickCheck[] }) {
  const [ans, setAns] = useState<Record<number, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const score = useMemo(
    () => items.reduce((s, q, i) => s + (ans[i] === q.dap_an ? 1 : 0), 0),
    [ans, items, submitted], // eslint-disable-line react-hooks/exhaustive-deps
  );
  if (items.length === 0) return <div className="lesson-empty">Chưa có câu hỏi.</div>;

  return (
    <div className="lesson-qc">
      {items.map((q, qi) => (
        <div className="lesson-qc-q" key={qi}>
          <div className="lesson-qc-cau">Câu {qi + 1}. {q.cau_hoi}</div>
          <div className="lesson-qc-opts">
            {q.lua_chon.map((op, oi) => {
              const picked = ans[qi] === oi;
              const isCorrect = q.dap_an === oi;
              const cls = "lesson-opt"
                + (picked ? " picked" : "")
                + (submitted && isCorrect ? " correct" : "")
                + (submitted && picked && !isCorrect ? " wrong" : "");
              return (
                <button key={oi} type="button" className={cls} disabled={submitted}
                  onClick={() => setAns((a) => ({ ...a, [qi]: oi }))}>
                  <span className="lesson-opt-k">{String.fromCharCode(65 + oi)}</span> {op}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {!submitted ? (
        <button className="btn accent" type="button"
          disabled={Object.keys(ans).length < items.length}
          onClick={() => setSubmitted(true)}>
          Nộp bài
        </button>
      ) : (
        <div className="lesson-qc-result">
          Kết quả: <b>{score}/{items.length}</b> câu đúng
          <button className="btn" type="button" style={{ marginLeft: 12 }}
            onClick={() => { setAns({}); setSubmitted(false); }}>Làm lại</button>
        </div>
      )}
    </div>
  );
}
