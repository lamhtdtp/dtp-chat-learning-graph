import { useMemo, useState } from "react";
import { ApiError, nopLuyenThem, rutLuyenThem } from "../api";
import type { CauCuoiKy, DeLuyenThem, KetQuaLuyenThem } from "../types";
import { escHtml } from "../mathHtml";
import { Cau } from "./CuoiKyView";
import { TroLyCard } from "./TroLyCard";

/** Lời nhắc cho một câu sai — dựng HOÀN TOÀN ở client từ kết quả server đã trả
 *  (nội dung câu, lựa chọn của em, đáp án, lời giải). KHÔNG gọi LLM, KHÔNG tốn lượt
 *  hỏi trợ lý — cùng lý do với `nhacCauSai` của Bài kiểm tra nhanh. Các trường HTML
 *  do server dựng sẵn thì dùng nguyên; chuỗi học sinh gõ (`chon`) và nhãn suy ra từ nó PHẢI qua `escHtml`. */
function nhacCauSai(c: CauCuoiKy, chon: string, dapAn: string, dapAnHtml: string, giaiHtml: string): string {
  const html = (key: string) => c.phuong_an.find((p) => p.key === key)?.html ?? "";
  const lietKe = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean)
    .map((k) => (c.dang === "TN1" || c.dang === "TNN") ? `<b>${escHtml(k)}.</b> ${html(k)}` : `<b>${escHtml(k)}</b>`)
    .join("; ");
  const daChon = chon.trim() ? `Em chọn ${c.dang === "DSN" ? `<b>${escHtml(chon)}</b>` : lietKe(chon)}, nhưng chưa đúng.`
    : "Câu này em chưa trả lời.";
  const dung = c.dang === "DSN"
    ? `Đáp án đúng là <b>${dapAnHtml}</b>.`
    : `Đáp án đúng là ${lietKe(dapAn)}.`;
  return `<p>${c.de_html}</p><p>${daChon} ${dung}</p>` + (giaiHtml ? `<p>${giaiHtml}</p>` : "");
}

/** Mục "Luyện thêm từ kho đề" (US-25) — ngay dưới Bài kiểm tra nhanh.
 *
 *  Câu do người biên soạn của DTP Testbank, đúng YCCĐ của bài; chấm ở máy chủ nên
 *  đáp án / lời giải chỉ có sau khi nộp. Chỉ rút khi học sinh bấm (không rút lúc mở bài:
 *  mỗi lần rút tốn lời gọi kho + model). Đủ 3 câu chấm được thì bài mới được xét đạt. */
export function LuyenThemView({ topicId, phanHien, onDocLai, onGraded }: {
  topicId: number;
  /** Các phần đang hiện — để đổi id phần thành emoji + tên người đọc hiểu được. */
  phanHien?: { id: string; ten: string; em: string }[];
  onDocLai?: (phan: string) => void;
  /** Gọi sau khi nộp xong để cập nhật vòng tiến độ / điểm thưởng bên ngoài. */
  onGraded?: () => void;
}) {
  const [de, setDe] = useState<DeLuyenThem | null>(null);
  const [chon, setChon] = useState<Record<string, string>>({});
  const [kq, setKq] = useState<KetQuaLuyenThem | null>(null);
  const [dang, setDang] = useState<"" | "rut" | "nop">("");
  const [loi, setLoi] = useState<string | null>(null);
  // Thẻ trợ lý theo qid câu sai: mở = có mặt trong tập.
  const [theCau, setTheCau] = useState<Set<string>>(new Set());
  const doiThe = (qid: string, mo: boolean) =>
    setTheCau((s) => { const n = new Set(s); mo ? n.add(qid) : n.delete(qid); return n; });

  const rut = async () => {
    setDang("rut"); setLoi(null); setKq(null); setChon({}); setTheCau(new Set());
    try {
      setDe(await rutLuyenThem(topicId));
    } catch (e) {
      setDe(null);
      setLoi(e instanceof ApiError ? e.message : "Chưa lấy được câu luyện thêm, thử lại nhé");
    } finally { setDang(""); }
  };

  const nop = async () => {
    if (!de?.de_id) return;
    setDang("nop"); setLoi(null);
    try {
      const r = await nopLuyenThem(de.de_id, chon);
      setKq(r);
      // Trợ lý chủ động ở câu sai ĐẦU TIÊN thôi, như Bài kiểm tra nhanh.
      const dau = r.cau.find((k) => k.cham_duoc && !k.dung);
      setTheCau(dau ? new Set([dau.qid]) : new Set());
      onGraded?.();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không nộp được bài, thử lại nhé");
    } finally { setDang(""); }
  };

  const kqTheoQid = useMemo(() => new Map(kq?.cau.map((k) => [k.qid, k]) ?? []), [kq]);
  const daTraLoi = de ? de.cau.filter((c) =>
    c.tu_cham && (chon[c.qid] ?? "").replace(/,/g, "").trim()).length : 0;
  const coDsn = de?.cau.some((c) => c.dang === "DSN") ?? false;
  const phanKien = phanHien?.find((p) => p.id === "kien_thuc");
  const pct = kq && kq.tong ? Math.round((kq.diem * 100) / kq.tong) : 0;

  return (
    <section className="lt-box" aria-label="Luyện thêm từ kho đề">
      <h3><span className="hi">📚</span> Luyện thêm từ kho đề</h3>

      {!de && (
        <div className="lt-mo">
          <p className="lt-sub">Tối đa 4 câu do người biên soạn của kho đề DTP Testbank, đúng các yêu
            cầu cần đạt của bài này. Làm xong em xem được đáp án và lời giải; làm đạt thì bài cũng
            được tính là đạt.</p>
          {loi && <div className="ot-loi" role="alert">⚠️ {loi}</div>}
          <button className="btn btn-primary" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
            {dang === "rut" ? "Đang lấy câu từ kho đề…" : "📚 Bắt đầu luyện thêm"}
          </button>
        </div>
      )}

      {/* Không có lượt nào (kho chưa có câu / bài chưa gắn YCCĐ): nói rõ, KHÔNG có nút nộp. */}
      {de && !de.de_id && (
        <div className="lt-mo">
          <div className="ck-thieu" role="status">ℹ️ {de.thong_bao}</div>
          <button className="btn" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
            {dang === "rut" ? "Đang lấy câu từ kho đề…" : "Thử lại"}
          </button>
        </div>
      )}

      {de?.de_id && (
        <>
          {de.thong_bao && !kq && <div className="ck-thieu" role="status">ℹ️ {de.thong_bao}</div>}

          {kq && (
            <div className={"lt-kq " + (kq.xet_dat ? (kq.dat_yeu_cau ? "ok" : "no") : "")} role="status">
              <div className="lt-diem">
                Đúng {kq.diem}/{kq.tong} câu{kq.khong_cham > 0 ? " chấm tự động" : ""}
                {kq.tong > 0 && <span className="num"> · {pct}%</span>}
              </div>
              {kq.khong_cham > 0 && (
                <div>{kq.khong_cham} câu không chấm tự động — em tự đối chiếu với lời giải.</div>
              )}
              {kq.xet_dat
                ? (kq.dat_yeu_cau
                  ? <div>🎉 Đạt yêu cầu! Bài này được tính là đạt.</div>
                  : <div>Chưa đạt (cần ≥70%).
                    {kq.trang_thai === "dat" && " Bài này vẫn đang ở trạng thái đạt."}</div>)
                : <div>{kq.ghi_chu}</div>}
            </div>
          )}

          <div className="ex-wrap">
            {de.cau.map((c) => {
              const k = kqTheoQid.get(c.qid);
              const sai = !!k && k.cham_duoc && !k.dung;
              return (
                <div key={c.qid} className="lt-cau">
                  <Cau c={c} chon={chon[c.qid] ?? ""} kq={k} anXemLai
                    onChon={(v) => setChon((s) => ({ ...s, [c.qid]: v }))} onMoBai={() => {}} />
                  {/* Phần của bài mà câu này kiểm tra. Kho không gắn câu vào phần cụ thể nên
                      luôn là "Kiến thức" (US-25 giả định 5). */}
                  {k && (
                    <div className="sai-nhac">
                      <div className="sn-d">📍 Câu này thuộc phần {phanKien ? `${phanKien.em} ${phanKien.ten}` : "Kiến thức"}</div>
                      {k.ycd && <div className="sn-y">Yêu cầu cần đạt: {k.ycd}</div>}
                      {onDocLai && (
                        <div className="sn-nut">
                          <button type="button" onClick={() => onDocLai("kien_thuc")}>↑ Đọc lại phần này</button>
                        </div>
                      )}
                    </div>
                  )}
                  {k && sai && (
                    theCau.has(c.qid) ? (
                      <TroLyCard topicId={topicId} anchor="kien_thuc"
                        nhan={`Câu ${c.stt}`} chuDong
                        noiDungSan={nhacCauSai(c, k.chon, k.dap_an, k.dap_an_html, k.giai_html)}
                        nguonSan={`Luyện thêm · Câu ${c.stt}`}
                        dapNhanh={[{ t: "Cho mình một ví dụ tương tự" }, { t: "Vì sao đáp án kia sai?" }]}
                        onDong={() => doiThe(c.qid, false)} />
                    ) : (
                      <button className="hoi-cau" type="button" onClick={() => doiThe(c.qid, true)}>
                        💬 Hỏi trợ lý về câu này
                      </button>
                    )
                  )}
                </div>
              );
            })}
          </div>

          {coDsn && !kq && (
            <div className="ck-tl">Câu điền đáp số: em viết số không dùng dấu chấm phân cách hàng nghìn
              (ví dụ 3510000, không viết 3.510.000).</div>
          )}
          {loi && <div className="ot-loi" role="alert">⚠️ {loi}</div>}
          {!kq ? (
            <div className="ot-nop">
              <span className="tnum">Đã trả lời {daTraLoi}/{de.so_cau_cham_duoc}</span>
              <button className="btn btn-primary" type="button" disabled={dang === "nop" || (!daTraLoi && de.so_cau_cham_duoc > 0)}
                onClick={() => void nop()}>{dang === "nop" ? "Đang chấm…" : "Nộp bài"}</button>
            </div>
          ) : (
            <div className="ot-nop">
              <span>Chấm ở máy chủ · lượt cũ vẫn được giữ kết quả.</span>
              <button className="btn" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
                {dang === "rut" ? "Đang lấy câu từ kho đề…" : "Luyện thêm lượt khác"}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
