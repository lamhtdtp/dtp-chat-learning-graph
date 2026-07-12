import { useState } from "react";
import { ApiError, generateExam } from "../api";
import { TUTOR_NAME } from "../config";
import { renderRich } from "../markdown";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import type { ExamQuestion, ExamResult } from "../types";

const MUC_DO_LABEL: Record<string, string> = { de: "Dễ", trung_binh: "Trung bình", kho: "Khó" };
const EMPTY_CITES = new Map();
const rich = (s: string) => renderRich(s, EMPTY_CITES, () => {});

function QuestionCard({ q, index }: { q: ExamQuestion; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="exam-q">
      <div className="exam-q-head">
        <span className="exam-q-no">Câu {index + 1}</span>
        <span className={`lv-badge ${q.muc_do}`}>{MUC_DO_LABEL[q.muc_do] ?? q.muc_do}</span>
      </div>
      <div className="bubble-text">{rich(q.noi_dung)}</div>
      <button className="exam-q-toggle" type="button" onClick={() => setOpen((v) => !v)}>
        {open ? "Ẩn đáp án" : "Xem đáp án & lời giải"}
      </button>
      {open && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
          <div><b style={{ color: "var(--accent-ink)" }}>Đáp án:</b> {rich(q.dap_an)}</div>
          {q.loi_giai && <div><b style={{ color: "var(--accent-ink)" }}>Lời giải:</b> {rich(q.loi_giai)}</div>}
        </div>
      )}
    </div>
  );
}

export function ExamView({ teacherName, onLogout }: { teacherName: string; onLogout: () => void }) {
  const [hocKy, setHocKy] = useState("hk1");
  const [soCau, setSoCau] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exam, setExam] = useState<ExamResult | null>(null);

  const run = async () => {
    setError(null); setBusy(true); setExam(null);
    try { setExam(await generateExam(hocKy, soCau)); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Không kết nối được máy chủ"); }
    finally { setBusy(false); }
  };

  return (
    <div className="exam-page" data-subject="toan">
      <div className="app-bar">
        <div className="brand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div className="brand-name">{TUTOR_NAME}</div>
        </div>
        <span className="pill-select" style={{ cursor: "default" }}>📐 Toán · Lớp 6</span>
        <div className="spacer" />
        <ThemeToggle />
        <UserMenu name={teacherName} role="giao_vien" onLogout={onLogout} />
      </div>

      <div className="exam-grid">
        <aside className="exam-cfg">
          <div className="exam-cfg-title">📝 Sinh đề theo ma trận</div>
          <label>Học kỳ
            <select value={hocKy} onChange={(e) => setHocKy(e.target.value)}>
              <option value="hk1">Học kỳ 1</option>
              <option value="hk2">Học kỳ 2</option>
            </select>
          </label>
          <label>Tổng số câu
            <input type="number" min={1} max={50} value={soCau}
              onChange={(e) => setSoCau(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} />
          </label>
          <div className="exam-total">Tổng số câu = {soCau}</div>
          <button className="exam-gen-btn" type="button" onClick={run} disabled={busy}>
            {busy ? "Đang sinh đề…" : "⚡ Sinh đề"}
          </button>
          <p style={{ fontSize: 12, color: "var(--ink-3)", margin: 0 }}>
            Đề bám ma trận đặc tả Toán 6; số câu mỗi mức độ khớp chính xác.
          </p>
        </aside>

        <main className="exam-preview">
          <div className="exam-pv-head">
            <div className="exam-pv-title">Sinh đề tự động</div>
            <div style={{ color: "var(--ink-3)", fontSize: 13 }}>Xin chào, thầy/cô {teacherName}</div>
          </div>

          {error && <div className="exam-warn">⚠️ {error}</div>}

          {!exam && !busy && !error && (
            <div className="exam-empty">
              <div style={{ fontSize: 40 }} aria-hidden>🧮</div>
              <div>Chọn học kỳ và số câu, rồi bấm “Sinh đề”.</div>
            </div>
          )}
          {busy && (
            <div className="exam-empty">
              <div style={{ fontSize: 40 }} aria-hidden>⏳</div>
              <div>Đang soạn đề bám ma trận, vui lòng chờ…</div>
            </div>
          )}

          {exam && (
            <>
              <div className="exam-pv-title" style={{ fontSize: 16 }}>
                Đề {exam.hoc_ky === "hk1" ? "Học kỳ 1" : "Học kỳ 2"} · {exam.cau_hoi.length}/{exam.tong_so_cau} câu
              </div>
              <div className="exam-chips">
                {Object.entries(exam.chi_tieu).map(([md, n]) => (
                  <span key={md} className={`exam-chip ${md === "trung_binh" ? "mid" : md === "kho" ? "hard" : "easy"}`}>
                    {MUC_DO_LABEL[md] ?? md}: {n} câu ({exam.ti_le_muc_do[md] ?? 0}%)
                  </span>
                ))}
              </div>
              {exam.canh_bao && <div className="exam-warn">⚠️ {exam.canh_bao}</div>}
              {exam.cau_hoi.map((q, i) => <QuestionCard key={i} q={q} index={i} />)}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
