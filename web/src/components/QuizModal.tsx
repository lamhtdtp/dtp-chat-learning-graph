import { useEffect, useState } from "react";
import { renderRich } from "../markdown";
import type { QuizData, QuizQuestion } from "../types";

// Bài trắc nghiệm i-Test tương tác (port từ repo dtp-chat-learning): chọn đáp án
// → Nộp bài → chấm điểm, hiện ✓/✕, Làm lại. Đề THẬT query trực tiếp i-Test.
// Backend phát các dạng: single / multi / fill (TF, MG đã được làm phẳng về single).
const NO_CITE = new Map();
const noop = () => {};
const rich = (s: string) => renderRich(s, NO_CITE, noop);
const letter = (i: number) => String.fromCharCode(65 + i);
const norm = (s: string) => (s || "").normalize("NFC").trim().toLowerCase().replace(/\s+/g, " ");

interface Props {
  loading: boolean;
  error?: string;
  data?: QuizData;
  onClose: () => void;
  onRetry: () => void;
}

function grade(q: QuizQuestion, r: unknown): { correct: number; total: number } {
  if (q.type === "single") {
    if (q.answer == null || q.answer < 0) return { correct: 0, total: 0 };
    return { correct: r === q.answer ? 1 : 0, total: 1 };
  }
  if (q.type === "multi") {
    const ans = q.answers ?? [];
    if (!ans.length) return { correct: 0, total: 0 };
    const picked = new Set<number>(Array.isArray(r) ? (r as number[]) : []);
    const ok = picked.size === ans.length && ans.every((a) => picked.has(a));
    return { correct: ok ? 1 : 0, total: 1 };
  }
  if (q.type === "fill") {
    const arr = (r as string[]) || [];
    let c = 0;
    (q.blanks ?? []).forEach((b, i) => {
      if (norm(arr[i] || "") === norm(b)) c++;
    });
    return { correct: c, total: (q.blanks ?? []).length };
  }
  return { correct: 0, total: 0 };
}

export function QuizModal({ loading, error, data, onClose, onRetry }: Props) {
  const [resp, setResp] = useState<Record<number, unknown>>({});
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    setResp({});
    setSubmitted(false);
  }, [data]);

  const questions = data?.questions ?? [];
  const score = questions.reduce(
    (acc, q, qi) => {
      if (!submitted) return acc;
      const g = grade(q, resp[qi]);
      return { correct: acc.correct + g.correct, total: acc.total + g.total };
    },
    { correct: 0, total: 0 },
  );

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card quiz-card" onClick={(e) => e.stopPropagation()}>
        <div className="quiz-head">
          <div className="quiz-head-info">
            <span className="quiz-logo">📝 i-Test</span>
            <div>
              <div className="quiz-title">{data?.title || "Bài trắc nghiệm"}</div>
              {!loading && !error && (
                <div className="quiz-sub">
                  {submitted
                    ? `Kết quả: ${score.correct}/${score.total} ý đúng`
                    : `${questions.length} câu · chọn đáp án rồi nộp bài`}
                </div>
              )}
            </div>
          </div>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Đóng">✕</button>
        </div>

        <div className="modal-body quiz-body">
          {loading && <div className="quiz-state">⏳ Đang tải đề trắc nghiệm cho em…</div>}
          {error && !loading && <div className="quiz-state err">😿 {error}</div>}
          {!loading && !error && questions.map((q, qi) => (
            <div className="quiz-q" key={qi}>
              <div className="quiz-q-stem">
                <span className="quiz-num">{qi + 1}</span>
                <span>{rich(q.q)}</span>
              </div>
              {q.image && (
                <img className="quiz-img" src={q.image} alt="Hình câu hỏi" loading="lazy" />
              )}
              <QuizBody q={q} qi={qi} resp={resp} submitted={submitted} setResp={setResp} />
            </div>
          ))}
        </div>

        {!loading && (
          <div className="quiz-foot">
            {error ? (
              <button className="quiz-btn primary" onClick={onRetry} type="button">↻ Thử lại</button>
            ) : submitted ? (
              <>
                <button className="quiz-btn ghost" onClick={() => { setResp({}); setSubmitted(false); }} type="button">↻ Làm lại</button>
                <button className="quiz-btn primary" onClick={onClose} type="button">Xong</button>
              </>
            ) : (
              <>
                <button className="quiz-btn ghost" onClick={onClose} type="button">Đóng</button>
                <button className="quiz-btn primary" onClick={() => setSubmitted(true)} type="button">Nộp bài</button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function choiceCls(showResult: boolean, isAns: boolean, isPicked: boolean): string {
  if (showResult && isAns) return "quiz-opt ok";
  if (showResult && isPicked && !isAns) return "quiz-opt wrong";
  if (!showResult && isPicked) return "quiz-opt picked";
  return "quiz-opt";
}

function QuizBody({
  q, qi, resp, submitted, setResp,
}: {
  q: QuizQuestion; qi: number; resp: Record<number, unknown>; submitted: boolean;
  setResp: React.Dispatch<React.SetStateAction<Record<number, unknown>>>;
}) {
  const opts = q.options ?? [];

  if (q.type === "single") {
    const picked = resp[qi] as number | undefined;
    const known = (q.answer ?? -1) >= 0;
    return (
      <div className="quiz-opts">
        {opts.map((opt, oi) => {
          const isAns = known && oi === q.answer;
          const isPicked = picked === oi;
          return (
            <button key={oi} type="button" disabled={submitted}
              className={choiceCls(submitted && known, isAns, isPicked)}
              onClick={() => setResp((r) => ({ ...r, [qi]: oi }))}>
              <span className="quiz-badge">{letter(oi)}</span>
              <span className="quiz-opt-text">{rich(opt)}</span>
              {submitted && isAns && <span className="quiz-tick ok">✓</span>}
              {submitted && known && isPicked && !isAns && <span className="quiz-tick no">✕</span>}
            </button>
          );
        })}
      </div>
    );
  }

  if (q.type === "multi") {
    const ans = q.answers ?? [];
    const sel = (resp[qi] as number[]) || [];
    return (
      <div className="quiz-opts">
        <div className="quiz-hint">Chọn nhiều đáp án</div>
        {opts.map((opt, oi) => {
          const isAns = ans.includes(oi);
          const isPicked = sel.includes(oi);
          return (
            <button key={oi} type="button" disabled={submitted}
              className={choiceCls(submitted, isAns, isPicked)}
              onClick={() => setResp((r) => {
                const cur = ((r[qi] as number[]) || []).slice();
                const at = cur.indexOf(oi);
                if (at >= 0) cur.splice(at, 1); else cur.push(oi);
                return { ...r, [qi]: cur };
              })}>
              <span className="quiz-badge square">{isPicked ? "✓" : ""}</span>
              <span className="quiz-opt-text">{rich(opt)}</span>
              {submitted && isAns && <span className="quiz-tick ok">✓</span>}
              {submitted && isPicked && !isAns && <span className="quiz-tick no">✕</span>}
            </button>
          );
        })}
      </div>
    );
  }

  // fill
  const arr = (resp[qi] as string[]) || [];
  return (
    <div className="quiz-opts">
      {(q.blanks ?? []).map((b, bi) => {
        const val = arr[bi] || "";
        const ok = submitted && norm(val) === norm(b);
        return (
          <div className="quiz-fill" key={bi}>
            <div className="quiz-fill-row">
              <span className="quiz-fill-label">Chỗ trống {bi + 1}:</span>
              <input value={val} disabled={submitted}
                className={submitted ? (ok ? "ok" : "wrong") : ""}
                onChange={(e) => setResp((r) => {
                  const cur = ((r[qi] as string[]) || []).slice();
                  cur[bi] = e.target.value;
                  return { ...r, [qi]: cur };
                })} />
            </div>
            {submitted && !ok && <span className="quiz-fill-ans">Đáp án: <b>{rich(b)}</b></span>}
          </div>
        );
      })}
    </div>
  );
}
