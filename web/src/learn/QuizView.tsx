import { useMemo, useState } from "react";
import { ApiError, submitQuiz } from "../api";
import type { QuizQuestion, QuizResult } from "../types";

const LV: Record<string, string> = { de: "Dễ", trung_binh: "Trung bình", kho: "Khó" };

/** Bài kiểm tra nhanh (trắc nghiệm) — chấm ở server, cập nhật tiến độ + XP.
 *  Style theo ex-card của mockup student-app. */
export function QuizView({ topicId, quiz, onGraded }: {
  topicId: number; quiz: QuizQuestion[]; onGraded?: (r: QuizResult) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [res, setRes] = useState<QuizResult | null>(null);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const allAnswered = useMemo(() => quiz.every((_, i) => answers[i] != null), [answers, quiz]);
  const pick = (qi: number, oi: number) => { if (!res) setAnswers((a) => ({ ...a, [qi]: oi })); };

  const submit = async () => {
    setSending(true); setErr(null);
    try {
      const r = await submitQuiz(topicId, quiz.map((_, i) => answers[i] ?? -1));
      setRes(r); onGraded?.(r);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không nộp được bài, thử lại nhé");
    } finally { setSending(false); }
  };
  const retry = () => { setAnswers({}); setRes(null); setErr(null); };

  return (
    <div className="ex-wrap">
      {quiz.map((q, qi) => {
        const rk = res?.ket_qua[qi];
        return (
          <div className="ex-card" key={qi}>
            <div className="ex-head">
              <span className={"ex-type " + q.lv}>{LV[q.lv] ?? "Câu hỏi"}</span>
            </div>
            <div className="ex-q" dangerouslySetInnerHTML={{ __html: `Câu ${qi + 1}. ${q.q}` }} />
            <div className="opts">
              {q.o.map((op, oi) => {
                const picked = answers[qi] === oi;
                const cls = ["opt"];
                if (!res && picked) cls.push("picked");
                if (res && rk) {
                  if (oi === rk.dap_an) cls.push("correct");
                  else if (picked) cls.push("wrong");
                }
                return (
                  <button key={oi} type="button" className={cls.join(" ")} disabled={!!res}
                    onClick={() => pick(qi, oi)}>
                    <span className="k">{String.fromCharCode(65 + oi)}</span>
                    <span dangerouslySetInnerHTML={{ __html: op }} />
                  </button>
                );
              })}
            </div>
            {res && rk?.giai && <div className="ex-giai" dangerouslySetInnerHTML={{ __html: rk.giai }} />}
          </div>
        );
      })}

      <div className="ex-foot">
        {!res ? (
          <button className="btn btn-primary" type="button" disabled={!allAnswered || sending} onClick={submit}>
            {sending ? "Đang chấm…" : "Nộp bài"}
          </button>
        ) : (
          <>
            <span className={"ex-fb " + (res.dat_yeu_cau ? "ok" : "no")}>
              {res.diem}/{res.tong} câu đúng {res.dat_yeu_cau ? "· 🎉 Đạt yêu cầu! +" + (res.diem * 5 + 10) + " XP" : "· cần ≥70%"}
            </span>
            <button className="btn" type="button" onClick={retry}>Làm lại</button>
          </>
        )}
        {err && <span className="ex-fb no">⚠️ {err}</span>}
      </div>
      <div className="gen-note">※ Bộ câu hỏi sinh tự động theo ma trận đặc tả (yêu cầu cần đạt + mức độ).</div>
    </div>
  );
}
