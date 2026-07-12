import { useState } from "react";
import { ApiError, generatePracticeExam } from "../api";
import { renderRich } from "../markdown";
import { Portal } from "./Portal";
import type { ExamQuestion, ExamResult } from "../types";

// Chip "Tạo một đề ngắn luyện tập": bấm -> sinh đề NGẮN bám ma trận đặc tả (gọi
// /exam/practice, cùng luồng service.sinh_de của giáo viên) -> hiện trong popup.
const MUC_DO_LABEL: Record<string, string> = { de: "Dễ", trung_binh: "Trung bình", kho: "Khó" };
const NO_CITE = new Map();
const rich = (s: string) => renderRich(s, NO_CITE, () => {});

function QCard({ q, i }: { q: ExamQuestion; i: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="exam-q">
      <div className="exam-q-head">
        <span className="exam-q-no">Câu {i + 1}</span>
        <span className={`lv-badge ${q.muc_do}`}>{MUC_DO_LABEL[q.muc_do] ?? q.muc_do}</span>
      </div>
      <div className="bubble-text">{rich(q.noi_dung)}</div>
      <button className="exam-q-toggle" type="button" onClick={() => setOpen((v) => !v)}>
        {open ? "Ẩn đáp án" : "Xem đáp án & lời giải"}
      </button>
      {open && (
        <div className="exam-q-ans">
          <div><b>Đáp án:</b> {rich(q.dap_an)}</div>
          {q.loi_giai && <div><b>Lời giải:</b> {rich(q.loi_giai)}</div>}
        </div>
      )}
    </div>
  );
}

export function PracticeExamChip({ label }: { label: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [exam, setExam] = useState<ExamResult | null>(null);

  const run = async () => {
    setOpen(true);
    setBusy(true);
    setErr(null);
    setExam(null);
    try {
      setExam(await generatePracticeExam());
    } catch (e) {
      setErr(e instanceof ApiError && e.message ? e.message : "Chưa tạo được đề, thử lại nhé.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button className="chip" type="button" onClick={run}>
        <span className="chip-arrow">→</span> {label}
      </button>

      {open && (
        <Portal>
        <div className="modal-scrim" onClick={() => setOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <span>📝 Đề ngắn luyện tập</span>
              <button className="modal-close" onClick={() => setOpen(false)} type="button" aria-label="Đóng">✕</button>
            </div>
            <div className="modal-body exam-modal-body">
              {busy && <div className="book-msg">⏳ Đang soạn đề bám ma trận, chờ chút nhé…</div>}
              {err && !busy && <div className="book-msg">{err}</div>}
              {exam && !busy && (
                <>
                  <div className="exam-sub">
                    Đề {exam.hoc_ky === "hk1" ? "Học kỳ 1" : "Học kỳ 2"} · {exam.cau_hoi.length}/{exam.tong_so_cau} câu
                  </div>
                  <div className="exam-chips">
                    {Object.entries(exam.chi_tieu).map(([md, n]) => (
                      <span key={md} className={`exam-chip ${md === "trung_binh" ? "mid" : md === "kho" ? "hard" : "easy"}`}>
                        {MUC_DO_LABEL[md] ?? md}: {n}
                      </span>
                    ))}
                  </div>
                  {exam.canh_bao && <div className="exam-warn">⚠️ {exam.canh_bao}</div>}
                  {exam.cau_hoi.map((q, i) => <QCard key={i} q={q} i={i} />)}
                </>
              )}
            </div>
          </div>
        </div>
        </Portal>
      )}
    </>
  );
}
