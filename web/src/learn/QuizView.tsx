import { useMemo, useState } from "react";
import { ApiError, submitQuiz } from "../api";
import type { Neo, QuizQuestion, QuizResult } from "../types";
import { renderMath } from "../mathHtml";
import { TroLyCard } from "./TroLyCard";

const LV: Record<string, string> = { de: "Dễ", trung_binh: "Trung bình", kho: "Khó" };
const AZ = (i: number) => String.fromCharCode(65 + i);

/** Lời nhắc cho một câu làm sai — dựng HOÀN TOÀN ở client từ kết quả server đã
 *  trả (`giai`, `dap_an`, lựa chọn của học sinh). KHÔNG gọi LLM, KHÔNG tốn lượt
 *  hỏi: đây là chỗ trợ lý chủ động phải rẻ, nếu không 20 lượt/ngày bay trong một
 *  bài kiểm tra. Học sinh muốn đào sâu thì hỏi tiếp trong chính thẻ (lúc đó mới
 *  tính lượt). */
function nhacCauSai(q: QuizQuestion, chon: number, dapAn: number, giai: string): string {
  const daChon = chon >= 0 && chon < q.o.length
    ? `Em chọn <b>${AZ(chon)}. ${renderMath(q.o[chon])}</b>, nhưng chưa đúng.`
    : "Câu này em chưa chọn đáp án nào.";
  const dung = `Đáp án đúng là <b>${AZ(dapAn)}. ${renderMath(q.o[dapAn] ?? "")}</b>.`;
  return `<p>${daChon} ${dung}</p>` + (giai ? `<p>${renderMath(giai)}</p>` : "");
}

/** Bài kiểm tra nhanh (trắc nghiệm) — chấm ở server, cập nhật tiến độ + XP.
 *  Style theo ex-card của mockup student-app. */
export function QuizView({ topicId, quiz, onGraded }: {
  topicId: number; quiz: QuizQuestion[]; onGraded?: (r: QuizResult) => void;
}) {
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [res, setRes] = useState<QuizResult | null>(null);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Thẻ trợ lý cho từng câu sai. Mở = có mặt trong tập; đóng thì bỏ ra.
  const [theCau, setTheCau] = useState<Set<number>>(new Set());
  const doiThe = (qi: number, mo: boolean) =>
    setTheCau((s) => { const n = new Set(s); mo ? n.add(qi) : n.delete(qi); return n; });

  const allAnswered = useMemo(() => quiz.every((_, i) => answers[i] != null), [answers, quiz]);
  const pick = (qi: number, oi: number) => { if (!res) setAnswers((a) => ({ ...a, [qi]: oi })); };

  const submit = async () => {
    setSending(true); setErr(null);
    try {
      const r = await submitQuiz(topicId, quiz.map((_, i) => answers[i] ?? -1));
      setRes(r); onGraded?.(r);
      // Trợ lý CHỦ ĐỘNG lên tiếng ở câu sai ĐẦU TIÊN thôi. Sai 5 câu mà bung 5
      // thẻ là một bức tường chữ ngay lúc học sinh đang nản; các câu còn lại để
      // nút, em nào muốn thì bấm.
      const dau = r.ket_qua.findIndex((k) => !k.dung);
      setTheCau(dau >= 0 ? new Set([dau]) : new Set());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không nộp được bài, thử lại nhé");
    } finally { setSending(false); }
  };
  const retry = () => { setAnswers({}); setRes(null); setErr(null); setTheCau(new Set()); };

  return (
    <div className="ex-wrap">
      {quiz.map((q, qi) => {
        const rk = res?.ket_qua[qi];
        return (
          <div className="ex-card" key={qi}>
            <div className="ex-head">
              <span className={"ex-type " + q.lv}>{LV[q.lv] ?? "Câu hỏi"}</span>
            </div>
            <div className="ex-q" dangerouslySetInnerHTML={{ __html: `Câu ${qi + 1}. ${renderMath(q.q)}` }} />
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
                    <span dangerouslySetInnerHTML={{ __html: renderMath(op) }} />
                  </button>
                );
              })}
            </div>
            {res && rk?.giai && <div className="ex-giai" dangerouslySetInnerHTML={{ __html: renderMath(rk.giai) }} />}

            {/* Trợ lý ở ngay chỗ học sinh vừa sai — nơi cần hỏi nhất mà trước đây
                lại là nơi duy nhất không có cách nào hỏi. */}
            {res && rk && !rk.dung && (
              theCau.has(qi) ? (
                <TroLyCard topicId={topicId} anchor={`quiz:${qi + 1}` as Neo}
                  nhan={`Câu ${qi + 1}`} chuDong
                  noiDungSan={nhacCauSai(q, rk.chon, rk.dap_an, rk.giai)}
                  nguonSan={`Bài kiểm tra · Câu ${qi + 1}`}
                  dapNhanh={[{ t: "Cho mình một ví dụ tương tự" }, { t: "Vì sao đáp án kia sai?" }]}
                  onDong={() => doiThe(qi, false)} />
              ) : (
                <button className="hoi-cau" type="button" onClick={() => doiThe(qi, true)}>
                  💬 Hỏi trợ lý về câu này
                </button>
              )
            )}
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
    </div>
  );
}
