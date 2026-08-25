import { useEffect, useMemo, useState } from "react";
import { ApiError, getDeOnTap, getOnTap, submitOnTap } from "../api";
import { renderMath } from "../mathHtml";
import type { DeOnTap, OnTap, QuizResult } from "../types";

const TT: Record<string, [string, string]> = {
  dat: ["ot-dat", "Đã đạt"], dang: ["ot-dang", "Đang học"], chua: ["ot-chua", "Chưa học"],
};
const LV: Record<string, string> = { de: "Dễ", trung_binh: "Trung bình", kho: "Khó" };
const AZ = (i: number) => String.fromCharCode(65 + i);

/** Ôn tập chương / cuối học kỳ (REQ §3.5).
 *
 *  KHÔNG phải bài mới: đây là *view* gộp các đơn vị trong một mạch (hoặc cả học
 *  kỳ) — danh sách bài kèm trạng thái, các ý phải nhớ, và một đề gom từ chính đề
 *  kiểm tra nhanh của từng bài. Gom lại chứ không sinh mới bằng AI: sinh mới sẽ
 *  lệch khỏi ma trận đặc tả và tốn AI cho thứ đã có sẵn. */
export function OnTapView({ phamVi, giaTri, ten, onMoBai, onDong }: {
  phamVi: "mach" | "hoc_ky";
  giaTri: string;
  ten: string;
  onMoBai: (topicId: number) => void;
  onDong: () => void;
}) {
  const [d, setD] = useState<OnTap | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [de, setDe] = useState<DeOnTap | null>(null);
  const [loiDe, setLoiDe] = useState<string | null>(null);
  const [dangTaiDe, setDangTaiDe] = useState(false);
  const [chon, setChon] = useState<Record<number, number>>({});
  const [kq, setKq] = useState<QuizResult | null>(null);
  const [dangNop, setDangNop] = useState(false);

  useEffect(() => {
    setD(null); setErr(null); setDe(null); setKq(null); setChon({}); setLoiDe(null);
    getOnTap(phamVi, giaTri)
      .catch((e) => { setErr(e instanceof ApiError ? e.message : "Không tải được nội dung ôn tập"); return null; })
      .then((r) => r && setD(r));
  }, [phamVi, giaTri]);

  const moDe = () => {
    setDangTaiDe(true); setLoiDe(null);
    getDeOnTap(phamVi, giaTri)
      .then(setDe)
      .catch((e) => setLoiDe(e instanceof ApiError ? e.message : "Không lấy được đề ôn tập"))
      .finally(() => setDangTaiDe(false));
  };

  const nop = async () => {
    if (!de) return;
    setDangNop(true); setLoiDe(null);
    try {
      const answers = de.cau.map((_, i) => (chon[i] ?? -1));
      setKq(await submitOnTap(phamVi, giaTri, answers));
    } catch (e) {
      setLoiDe(e instanceof ApiError ? e.message : "Không nộp được bài");
    } finally { setDangNop(false); }
  };

  const daTraLoi = useMemo(
    () => (de ? de.cau.filter((_, i) => chon[i] !== undefined).length : 0), [de, chon]);

  if (err) return <div className="lesson-empty">⚠️ {err}</div>;
  if (!d) return null;

  return (
    <div className="lesson ot">
      <div className="ot-top">
        <span className="badge-hoc">🔁 ÔN TẬP {phamVi === "mach" ? "CHƯƠNG" : "CUỐI KỲ"}</span>
        <button className="ot-dong" type="button" onClick={onDong}>← Về bài học</button>
      </div>
      <h1>{ten}</h1>
      <p className="ot-sub">
        {d.so_bai} bài trong phạm vi này
        {d.chua_xong > 0 ? ` · còn ${d.chua_xong} bài chưa đạt` : " · đã đạt hết"}
        {d.ycd > 0 && ` · ${d.ycd} yêu cầu cần đạt`}
      </p>

      <h3><span className="hi">📗</span> Các bài cần ôn
        <span className="so-phan tnum">{d.so_bai}</span></h3>
      <div className="ot-bai">
        {d.bai.map((b) => {
          const [cls, nhan] = TT[b.trang_thai];
          return (
            <button className="ot-row" type="button" key={b.topic_id}
              onClick={() => onMoBai(b.topic_id)}
              title={b.co_noi_dung ? "Mở lại bài này" : "Bài này chưa có nội dung"}>
              <span className={"ot-pill " + cls}>{nhan}</span>
              <span className="ot-ten">{b.ten}</span>
              {!b.co_noi_dung && <span className="ot-ghi">chưa soạn</span>}
              <span className="ot-mui" aria-hidden>↗</span>
            </button>
          );
        })}
      </div>

      {d.can_nho.length > 0 && (
        <>
          <h3 className="kt"><span className="hi">📌</span> Cần nhớ
            <span className="so-phan tnum">{d.can_nho.length}</span></h3>
          {/* Gom từ blockquote trong Kiến thức trọng tâm — chỗ chuyên gia đã đánh
              dấu là phải nhớ, không nhờ AI viết lại. */}
          <ul className="ot-nho">
            {d.can_nho.map((c, i) => (
              <li key={i}>
                <span dangerouslySetInnerHTML={{ __html: renderMath(c.y) }} />
                <em>{c.ten}</em>
              </li>
            ))}
          </ul>
        </>
      )}

      <h3><span className="hi">✅</span> Kiểm tra ôn tập
        <span className="so-phan tnum">{d.so_cau_de} câu</span></h3>

      {!de && (
        <div className="ot-mo">
          <p>Đề gom từ chính bài kiểm tra nhanh của {d.so_bai_co_de}/{d.so_bai} bài trên
            — bám ma trận đặc tả, không sinh câu mới.</p>
          {/* Nói rõ khi chưa gom đủ chỉ tiêu: hứa 12 câu rồi đưa 8 là nói sai. */}
          {d.so_cau_de > 0 && d.so_cau_de < d.so_cau_toi_da && (
            <p className="ot-it">Mới gom được {d.so_cau_de}/{d.so_cau_toi_da} câu vì
              {" "}{d.so_bai - d.so_bai_co_de} bài chưa có bài kiểm tra nhanh.</p>
          )}
          {loiDe && <div className="ot-loi">⚠️ {loiDe}</div>}
          {d.so_cau_de === 0
            ? <div className="ot-loi">Chưa bài nào trong mạch này có bài kiểm tra nhanh,
                nên chưa gom được đề ôn tập.</div>
            : <button className="btn-primary" type="button" disabled={dangTaiDe} onClick={moDe}>
                {dangTaiDe ? "Đang gom đề…" : `Bắt đầu ôn tập (${d.so_cau_de} câu)`}
              </button>}
        </div>
      )}

      {de && (
        <div className="ot-de">
          {de.cau.map((c, i) => {
            const k = kq?.ket_qua[i];
            return (
              <div className={"ot-cau" + (k ? (k.dung ? " dung" : " sai") : "")} key={i}>
                <div className="ot-ch">
                  <b className="tnum">Câu {i + 1}</b>
                  <span className="ot-lv">{LV[c.lv] ?? c.lv}</span>
                  <span className="ot-tu">{c.bai}</span>
                </div>
                <div className="ot-q" dangerouslySetInnerHTML={{ __html: renderMath(c.q) }} />
                <div className="ot-opts">
                  {c.o.map((o, oi) => {
                    const daChon = chon[i] === oi;
                    const dungAn = k && k.dap_an === oi;
                    const saiChon = k && k.chon === oi && !k.dung;
                    return (
                      <button key={oi} type="button" disabled={!!kq}
                        className={"ot-opt" + (daChon ? " chon" : "")
                          + (dungAn ? " dung" : "") + (saiChon ? " sai" : "")}
                        onClick={() => setChon((v) => ({ ...v, [i]: oi }))}>
                        <span className="ot-az">{AZ(oi)}</span>
                        <span dangerouslySetInnerHTML={{ __html: renderMath(o) }} />
                        {dungAn && <span className="ot-dau" aria-hidden>✔</span>}
                        {saiChon && <span className="ot-dau" aria-hidden>✘</span>}
                      </button>
                    );
                  })}
                </div>
                {k?.giai && (
                  <div className="ot-giai" dangerouslySetInnerHTML={{ __html: renderMath(k.giai) }} />
                )}
              </div>
            );
          })}

          {loiDe && <div className="ot-loi">⚠️ {loiDe}</div>}

          {kq ? (
            <div className={"ot-kq " + (kq.dat_yeu_cau ? "dat" : "chua")}>
              <b>{kq.dat_yeu_cau ? "🎉 Đạt yêu cầu!" : "Chưa đạt — ôn lại rồi thử lần nữa nhé."}</b>
              <span>Đúng <b className="tnum">{kq.diem}/{kq.tong}</b></span>
              <button className="btn-primary" type="button"
                onClick={() => { setKq(null); setChon({}); moDe(); }}>Làm lại →</button>
            </div>
          ) : (
            <div className="ot-nop">
              <span className="tnum">Đã trả lời {daTraLoi}/{de.so_cau}</span>
              <button className="btn-primary" type="button" disabled={dangNop || !daTraLoi}
                onClick={() => void nop()}>{dangNop ? "Đang chấm…" : "Nộp bài"}</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
