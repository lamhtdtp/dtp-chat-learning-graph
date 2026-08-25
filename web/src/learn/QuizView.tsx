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

/** Bài kiểm tra nhanh (trắc nghiệm) — chấm ở server, cập nhật tiến độ.
 *  Style theo ex-card của mockup student-app. */
export function QuizView({ topicId, quiz, onGraded, phanHien, onDocLai, onHoiPhan }: {
  topicId: number; quiz: QuizQuestion[]; onGraded?: (r: QuizResult) => void;
  /** Các phần đang hiện — để đổi id phần thành emoji + tên người đọc hiểu được. */
  phanHien?: { id: string; ten: string; em: string }[];
  /** Cuộn tới phần đó + loé viền (§3.4). */
  onDocLai?: (phan: string) => void;
  /** Mở thẻ trợ lý neo vào phần đó. */
  onHoiPhan?: (phan: string, ten: string) => void;
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
            {/* §3.4 — câu SAI thì chỉ thẳng phần cần đọc lại. Không có `phan`
                (đề sinh trước khi có khoá này) thì không hiện khối rỗng. */}
            {res && rk && !rk.dung && rk.phan && (() => {
              const p = phanHien?.find((x) => x.id === rk.phan);
              return (
                <div className="sai-nhac">
                  <div className="sn-d">📍 Câu này thuộc phần {p ? `${p.em} ${p.ten}` : rk.phan}</div>
                  {rk.ycd && <div className="sn-y">Yêu cầu cần đạt: {rk.ycd}</div>}
                  <div className="sn-nut">
                    {onDocLai && <button type="button" onClick={() => onDocLai(rk.phan!)}>↑ Đọc lại phần này</button>}
                    {onHoiPhan && <button type="button"
                      onClick={() => onHoiPhan(rk.phan!, p?.ten ?? rk.phan!)}>💬 Hỏi trợ lý về đoạn đó</button>}
                  </div>
                </div>
              );
            })()}

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

      {/* Gom TẤT CẢ phần cần đọc lại, khử trùng, GIỮ thứ tự trong bài — sắp theo
          số câu sai sẽ làm mất mạch đọc của học sinh. */}
      {res && (() => {
        const sai = res.ket_qua.filter((k) => !k.dung && k.phan).map((k) => k.phan!);
        const ds = (phanHien ?? []).filter((p) => sai.includes(p.id));
        if (!ds.length) return null;
        return (
          <div className="on-lai">
            <b>💡 Nên đọc lại {ds.length} phần trước khi làm lại</b>
            <div className="ol-ds">
              {ds.map((p) => (
                <button className="chip" type="button" key={p.id} onClick={() => onDocLai?.(p.id)}>
                  {p.em} {p.ten}
                </button>
              ))}
            </div>
          </div>
        );
      })()}

      <div className="ex-foot">
        {!res ? (
          <button className="btn btn-primary" type="button" disabled={!allAnswered || sending} onClick={submit}>
            {sending ? "Đang chấm…" : "Nộp bài"}
          </button>
        ) : (
          <>
            <span className={"ex-fb " + (res.dat_yeu_cau ? "ok" : "no")}>
              {/* Không hiện "+N XP" nữa: XP đã bỏ khỏi giao diện học sinh. Bỏ luôn
                  công thức `diem*5+10` — nó nhân bản cách tính của server, sửa
                  một bên là hai bên lệch mà không ai biết. */}
              {res.diem}/{res.tong} câu đúng {res.dat_yeu_cau ? "· 🎉 Đạt yêu cầu!" : "· cần ≥70%"}
            </span>
            <button className="btn" type="button" onClick={retry}>Làm lại</button>
          </>
        )}
        {err && <span className="ex-fb no">⚠️ {err}</span>}
      </div>
    </div>
  );
}
