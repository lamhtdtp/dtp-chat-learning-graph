import { useState } from "react";
import { ApiError, generateExam } from "../api";
import { APP_NAME } from "../config";
import type { ExamQuestion, ExamResult } from "../types";
import { renderRich } from "../markdown";

const MUC_DO_LABEL: Record<string, string> = {
  de: "Dễ",
  trung_binh: "Trung bình",
  kho: "Khó",
};

const EMPTY_CITES = new Map();

function QuestionCard({ q, index }: { q: ExamQuestion; index: number }) {
  const [showAnswer, setShowAnswer] = useState(false);
  return (
    <div className="exam-q">
      <div className="exam-q-head">
        <span className="exam-q-no">Câu {index + 1}</span>
        <span className={`exam-q-level lv-${q.muc_do}`}>{MUC_DO_LABEL[q.muc_do] ?? q.muc_do}</span>
      </div>
      <div className="exam-q-body">{renderRich(q.noi_dung, EMPTY_CITES, () => {})}</div>
      <button className="exam-q-toggle" type="button" onClick={() => setShowAnswer((v) => !v)}>
        {showAnswer ? "Ẩn đáp án" : "Xem đáp án & lời giải"}
      </button>
      {showAnswer && (
        <div className="exam-q-answer">
          <div className="exam-ans-line"><b>Đáp án:</b> {renderRich(q.dap_an, EMPTY_CITES, () => {})}</div>
          {q.loi_giai && <div className="exam-ans-line"><b>Lời giải:</b> {renderRich(q.loi_giai, EMPTY_CITES, () => {})}</div>}
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
    setError(null);
    setBusy(true);
    setExam(null);
    try {
      setExam(await generateExam(hocKy, soCau));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được máy chủ");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="exam-screen">
      <aside className="exam-side">
        <div className="exam-brand">
          <div className="box"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div>
            <div className="t">Gia sư DTP</div>
            <div className="s">{APP_NAME}</div>
          </div>
        </div>

        <div className="exam-form">
          <div className="exam-form-title">📝 Sinh đề kiểm tra</div>
          <label>
            Học kỳ
            <select value={hocKy} onChange={(e) => setHocKy(e.target.value)}>
              <option value="hk1">Học kỳ 1</option>
              <option value="hk2">Học kỳ 2</option>
            </select>
          </label>
          <label>
            Tổng số câu
            <input
              type="number"
              min={1}
              max={50}
              value={soCau}
              onChange={(e) => setSoCau(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
            />
          </label>
          <button className="btn-primary" type="button" onClick={run} disabled={busy}>
            {busy ? "Đang sinh đề…" : "Sinh đề theo ma trận"}
          </button>
          <p className="exam-hint">Đề bám ma trận đặc tả Toán 6, số câu mỗi mức độ khớp chính xác.</p>
        </div>

        <button className="exam-logout" type="button" onClick={onLogout}>Đăng xuất</button>
      </aside>

      <main className="exam-main">
        <header className="exam-header">
          <div>
            <div className="exam-h-title">Sinh đề tự động</div>
            <div className="exam-h-sub">Xin chào, thầy/cô {teacherName}</div>
          </div>
        </header>

        <div className="exam-content">
          {error && <div className="exam-error">{error}</div>}

          {!exam && !busy && !error && (
            <div className="exam-empty">
              <div className="exam-empty-ic">🧮</div>
              <div className="exam-empty-t">Chọn học kỳ và số câu, rồi bấm “Sinh đề theo ma trận”.</div>
            </div>
          )}

          {busy && (
            <div className="exam-empty">
              <div className="exam-empty-ic">⏳</div>
              <div className="exam-empty-t">Đang soạn đề bám ma trận, vui lòng chờ…</div>
            </div>
          )}

          {exam && (
            <>
              <div className="exam-summary">
                <div className="exam-sum-title">
                  Đề {exam.hoc_ky === "hk1" ? "Học kỳ 1" : "Học kỳ 2"} · {exam.cau_hoi.length}/{exam.tong_so_cau} câu
                </div>
                <div className="exam-chips">
                  {Object.entries(exam.chi_tieu).map(([md, n]) => (
                    <span key={md} className={`exam-chip lv-${md}`}>
                      {MUC_DO_LABEL[md] ?? md}: {n} câu ({exam.ti_le_muc_do[md] ?? 0}%)
                    </span>
                  ))}
                </div>
                {exam.canh_bao && <div className="exam-warn">⚠️ {exam.canh_bao}</div>}
              </div>

              <div className="exam-list">
                {exam.cau_hoi.map((q, i) => (
                  <QuestionCard key={i} q={q} index={i} />
                ))}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
