import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, dsDeCuoiKy, moDeCuoiKy, nopDeCuoiKy, rutDeCuoiKy } from "../api";
import type { CauCuoiKy, DeCuoiKy, DeCuoiKyTomTat, KetQuaCau, KetQuaCuoiKy } from "../types";

const MUC: Record<string, [string, string]> = {
  B: ["de", "Biết"], H: ["trung_binh", "Hiểu"], V: ["kho", "Vận dụng"],
};
const DANG: Record<string, string> = {
  TN1: "Một đáp án", TNN: "Nhiều đáp án", DS: "Đúng / Sai", DSN: "Điền đáp số", TL: "Tự luận",
};
/** Số câu của "bài làm mới": 2 câu mỗi chỗ còn yếu, trong khoảng 4–12. Ít hơn
 *  thì một chỗ một câu, làm đúng một câu chưa nói lên gì; nhiều hơn thì thành
 *  làm lại cả đề. */
const soCauDeMoi = (n: number) => Math.min(12, Math.max(4, n * 2));

/** Nháp đáp án của đề CHƯA nộp, theo de_id. Lỡ đóng tab hay tải lại giữa chừng
 *  thì mở lại đề vẫn còn những gì đã chọn. Chỉ là tiện ích của riêng trình duyệt
 *  này — localStorage có thể không dùng được (chế độ ẩn danh…) nên mọi lần đọc /
 *  ghi đều bọc try/catch, hỏng thì thôi không lưu. */
const NHAP = (deId: string) => `ck-nhap:${deId}`;
function docNhap(deId: string): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(NHAP(deId)) ?? "{}") ?? {}; } catch { return {}; }
}
function ghiNhap(deId: string, v: Record<string, string>) {
  try { localStorage.setItem(NHAP(deId), JSON.stringify(v)); } catch { /* bỏ qua */ }
}
function xoaNhap(deId: string) {
  try { localStorage.removeItem(NHAP(deId)); } catch { /* bỏ qua */ }
}
const ngayGio = (iso: string) => {
  const d = new Date(iso);
  return isNaN(+d) ? iso : d.toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

/** Một câu, cả lúc làm lẫn sau khi nộp. `chon` luôn là CHUỖI nhãn như server
 *  nhận ("B", "A,C", "Đ,S,Đ,S", "3,5") — không giữ chỉ số phương án. */
function Cau({ c, chon, onChon, kq, onMoBai }: {
  c: CauCuoiKy;
  chon: string;
  onChon: (v: string) => void;
  kq?: KetQuaCau;
  onMoBai: (topicId: number, phan?: string) => void;
}) {
  const [cls, ten] = MUC[c.muc_do] ?? ["", c.muc_do];
  const daNop = !!kq;
  const daChon = new Set(chon.split(",").filter(Boolean));
  const dungKeys = new Set((kq?.dap_an ?? "").split(",").map((x) => x.trim()));

  // DS: mỗi ý một ô Đ/S, giữ vị trí kể cả ý bỏ trống ("Đ,,S,").
  const yDs = c.dang === "DS" ? c.phuong_an.map((_, i) => chon.split(",")[i] ?? "") : [];
  const yDsDung = c.dang === "DS" ? (kq?.dap_an ?? "").split(",").map((x) =>
    (x.trim().toUpperCase() === "D" ? "Đ" : x.trim().toUpperCase())) : [];
  const datDs = (i: number, v: string) => {
    const a = [...yDs]; a[i] = a[i] === v ? "" : v; onChon(a.join(","));
  };

  const bam = (k: string) => {
    if (daNop) return;
    if (c.dang === "TNN") {
      const s = new Set(daChon);
      s.has(k) ? s.delete(k) : s.add(k);
      onChon([...s].sort().join(","));
    } else onChon(k);
  };

  return (
    <div className="ex-card ck-cau" id={`ck-cau-${c.stt}`}>
      <div className="ex-head">
        <span className={"ex-type " + cls}>{ten}</span>
        <span className="ck-dang">{DANG[c.dang] ?? c.dang}</span>
        {c.don_vi && <span className="ck-dv" title={c.ycd}>{c.don_vi}</span>}
      </div>
      {c.cau_dan && <div className="ck-dan">{c.cau_dan}</div>}
      {c.du_kien_html && <div className="ck-dukien" dangerouslySetInnerHTML={{ __html: c.du_kien_html }} />}
      <div className="ex-q ck-q">
        <b>Câu {c.stt}.</b> <span dangerouslySetInnerHTML={{ __html: c.de_html }} />
        {c.dang === "TNN" && <i className="ck-goi"> (chọn tất cả đáp án đúng)</i>}
      </div>

      {(c.dang === "TN1" || c.dang === "TNN") && (
        <div className="opts">
          {c.phuong_an.map((p) => {
            const laDung = dungKeys.has(p.key);
            const chonP = daChon.has(p.key);
            const ld = kq?.ly_do[p.key];
            const boc = daNop ? (laDung ? "dung" : chonP ? "sai" : "") : "";
            const optCls = ["opt"];
            if (!daNop && chonP) optCls.push("picked");
            if (daNop && laDung) optCls.push("correct");
            else if (daNop && chonP) optCls.push("wrong");
            return (
              <div className={"b4-pa " + boc} key={p.key}>
                <button type="button" className={optCls.join(" ")} disabled={daNop}
                  aria-pressed={chonP} onClick={() => bam(p.key)}>
                  <span className="k">{p.key}</span>
                  <span dangerouslySetInnerHTML={{ __html: p.html }} />
                  {/* Trạng thái nói bằng dấu, không chỉ bằng màu. */}
                  {daNop && laDung && <span className="ck-dau" aria-label="đáp án đúng">✓</span>}
                  {daNop && chonP && !laDung && <span className="ck-dau" aria-label="em chọn sai">✗</span>}
                </button>
                {daNop && ld && (
                  <div className="opt-ly">
                    <span className="nhan">
                      {laDung ? "✓ Vì sao đúng" : chonP ? "✗ Vì sao em sai" : "– Vì sao không chọn"}
                    </span>
                    {ld.noi_dung}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {c.dang === "DS" && (
        <div className="ck-ds">
          {c.phuong_an.map((p, i) => {
            const ld = kq?.ly_do[p.key];
            const dungY = yDsDung[i];
            const saiY = daNop && yDs[i] !== dungY;
            return (
              <div className={"b4-pa " + (daNop ? (saiY ? "sai" : "dung") : "")} key={p.key}>
                <div className={"opt ck-y" + (daNop ? (saiY ? " wrong" : " correct") : "")}>
                  <span className="k">{p.key}</span>
                  <span className="ck-y-tx" dangerouslySetInnerHTML={{ __html: p.html }} />
                  <span className="ck-ds-nut" role="group" aria-label={`Ý ${p.key} đúng hay sai`}>
                    {["Đ", "S"].map((v) => (
                      <button key={v} type="button" disabled={daNop}
                        className={yDs[i] === v ? "on" : ""} aria-pressed={yDs[i] === v}
                        onClick={() => datDs(i, v)}>{v === "Đ" ? "Đúng" : "Sai"}</button>
                    ))}
                  </span>
                </div>
                {daNop && (
                  <div className="opt-ly">
                    <span className="nhan">{saiY ? "✗" : "✓"} Ý này {dungY === "Đ" ? "ĐÚNG" : "SAI"}</span>
                    {ld?.noi_dung ?? (saiY ? `Em chọn ${yDs[i] ? (yDs[i] === "Đ" ? "Đúng" : "Sai") : "bỏ trống"}.` : "")}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {c.dang === "DSN" && (
        <div className="ck-dsn">
          <label>
            <span>Đáp số:</span>
            <input type="text" inputMode="decimal" maxLength={60} value={chon} disabled={daNop}
              placeholder="Nhập đáp số" onChange={(e) => onChon(e.target.value)} />
          </label>
          {daNop && (
            <div className={"ck-dsn-kq " + (kq!.dung ? "ok" : "no")}>
              {kq!.dung ? "✓ Đúng" : "✗ Chưa đúng"} · Đáp án:{" "}
              <b dangerouslySetInnerHTML={{ __html: kq!.dap_an_html }} />
            </div>
          )}
        </div>
      )}

      {!c.tu_cham && (
        <div className="ck-tl">
          {c.dang === "TL"
            ? "Câu tự luận — em làm ra giấy, so với lời giải sau khi nộp. Câu này không tính vào điểm."
            : "Câu này không chấm tự động được — so với lời giải sau khi nộp. Không tính vào điểm."}
        </div>
      )}

      {daNop && kq!.giai_html && (
        <div className="ex-giai"><b>Lời giải:</b> <span dangerouslySetInnerHTML={{ __html: kq!.giai_html }} /></div>
      )}
      {daNop && kq!.cham_duoc && (
        <div className="ex-foot">
          <span className={"ex-fb " + (kq!.dung ? "ok" : "no")}>
            {kq!.dung ? "✓ Đúng rồi!" : "✗ Chưa đúng"}
            {kq!.so_y != null && !kq!.dung && ` · đúng ${kq!.so_y_dung}/${kq!.so_y} ý`}
          </span>
          {!kq!.dung && kq!.topic_id != null && (
            <button className="hoi-cau" type="button" onClick={() => onMoBai(kq!.topic_id!, "kien_thuc")}>
              📚 Xem lại bài: {kq!.don_vi}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Đề cuối kỳ rút từ DTP Testbank (bước ②③④ của demo).
 *
 *  Đáp án KHÔNG có ở client trước khi nộp — server chấm, rồi mới trả đáp án,
 *  lời giải và lý do từng phương án. Kết quả chấm theo YÊU CẦU CẦN ĐẠT (khoá bền
 *  `ar_id`), không theo số câu: đề sinh lại thì số câu đổi, YCCĐ thì không. */
export function CuoiKyView({ exam, ten, moDe, onMoBai, onDong }: {
  exam: string;
  ten: string;
  /** Mở thẳng đề này (bấm từ Hồ sơ học tập) thay vì màn bắt đầu. */
  moDe?: string;
  onMoBai: (topicId: number, phan?: string) => void;
  onDong: () => void;
}) {
  const [de, setDe] = useState<DeCuoiKy | null>(null);
  const [chon, setChon] = useState<Record<string, string>>({});
  const [kq, setKq] = useState<KetQuaCuoiKy | null>(null);
  const [dang, setDang] = useState<"" | "rut" | "nop">("");
  const [loi, setLoi] = useState<string | null>(null);
  // "Bài làm mới" chỉ trong các YCCĐ còn yếu -> ghi lại để tiêu đề nói đúng.
  const [onLai, setOnLai] = useState(false);
  // Khung cuộn là cột `.main`, không phải window — window.scrollTo không làm gì.
  const dau = useRef<HTMLDivElement>(null);
  // Cuộn SAU khi đã render: gọi ngay lúc setState thì khối kết quả chèn vào phía
  // trên giữa chừng, cuộn mượt bị cắt ngang và học sinh đứng lại giữa đề.
  const [cuon, setCuon] = useState(0);
  const veDau = () => setCuon((n) => n + 1);
  useEffect(() => {
    if (cuon) dau.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cuon]);

  // Lịch sử đề của kỳ này — tải lại mỗi lần về màn bắt đầu, để đề vừa nộp hiện ngay.
  const [ds, setDs] = useState<DeCuoiKyTomTat[] | null>(null);
  useEffect(() => {
    if (de) return;
    dsDeCuoiKy(exam).then((r) => setDs(r.de)).catch(() => setDs([]));
  }, [de, exam]);

  /** Mở lại một đề: đã nộp -> hiện nguyên kết quả cũ; chưa nộp -> làm tiếp từ nháp. */
  const mo = async (deId: string, onLaiDe = false) => {
    setDang("rut"); setLoi(null);
    try {
      const d = await moDeCuoiKy(deId);
      const k = d.ket_qua ?? null;
      setDe(d); setKq(k); setOnLai(onLaiDe || !!d.on_lai);
      // Đã nộp: dựng lại lựa chọn từ kết quả để các ô hiện đúng em đã chọn gì.
      setChon(k ? Object.fromEntries(k.cau.map((c) => [c.qid, c.chon])) : docNhap(deId));
      veDau();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không mở được đề, thử lại nhé");
    } finally { setDang(""); }
  };
  useEffect(() => { if (moDe) void mo(moDe); }, [moDe]); // eslint-disable-line

  // Lưu nháp khi đang làm (chưa nộp).
  useEffect(() => {
    if (de?.de_id && !kq && Object.keys(chon).length) ghiNhap(de.de_id, chon);
  }, [de, kq, chon]);

  const rut = async (arIds?: string[]) => {
    setDang("rut"); setLoi(null);
    try {
      const d = await rutDeCuoiKy({ exam, arIds, total: arIds?.length ? soCauDeMoi(arIds.length) : 12 });
      setDe(d); setChon({}); setKq(null); setOnLai(!!arIds?.length);
      veDau();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không rút được đề, thử lại nhé");
    } finally { setDang(""); }
  };

  const nop = async () => {
    if (!de?.de_id) return;
    setDang("nop"); setLoi(null);
    try {
      setKq(await nopDeCuoiKy(de.de_id, chon));
      xoaNhap(de.de_id);
      veDau();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không nộp được bài, thử lại nhé");
    } finally { setDang(""); }
  };

  const daTraLoi = useMemo(() => (de ? de.cau.filter((c) =>
    c.tu_cham && (chon[c.qid] ?? "").replace(/,/g, "").trim()).length : 0), [de, chon]);
  const tuCham = de?.cau.filter((c) => c.tu_cham).length ?? 0;
  const kqTheoQid = useMemo(() => new Map(kq?.cau.map((k) => [k.qid, k]) ?? []), [kq]);

  return (
    <div className="lesson ck" ref={dau}>
      <div className="ot-top">
        <span className="badge-hoc">📝 ĐỀ {onLai ? "ÔN LẠI CHỖ CÒN YẾU" : "CUỐI KỲ"}</span>
        {de && (
          <button className="ot-dong" type="button" onClick={() => { setDe(null); setKq(null); }}>
            ☰ Các lần làm</button>
        )}
        <button className="ot-dong ck-ve" type="button" onClick={onDong}>← Về bài học</button>
      </div>
      <h1>{ten}</h1>

      {!de && (
        <div className="ck-mo">
          <p className="ot-sub">12 câu rút từ kho đề ôn luyện của DTP Testbank, đúng tỉ lệ ma trận:
            5 câu Biết · 4 câu Hiểu · 3 câu Vận dụng. Làm xong em xem được vì sao từng phương án
            đúng hay sai, và kết quả theo từng yêu cầu cần đạt.</p>
          {loi && <div className="ot-loi">⚠️ {loi}</div>}
          <button className="btn btn-primary" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
            {dang === "rut" ? "Đang rút đề…" : "Bắt đầu làm đề →"}
          </button>
          {ds && ds.length > 0 && <LichSu ds={ds} onMo={(x) => void mo(x.de_id, x.on_lai)} />}
        </div>
      )}

      {de && !de.cau.length && (
        <div className="ck-mo">
          <div className="ot-loi">⚠️ {de.thong_bao || "Kho chưa có câu nào cho đề này."}</div>
          <button className="btn" type="button" onClick={() => setDe(null)}>← Quay lại</button>
        </div>
      )}

      {de && de.cau.length > 0 && (
        <>
          {/* Testbank thiếu câu thì BÁO THIẾU, không lấy mức khác bù — nói thẳng
              với học sinh thay vì lặng lẽ đưa ra một đề ngắn hơn đã hứa. */}
          {!de.du_cau && de.thong_bao && (
            <div className="ck-thieu" role="status">ℹ️ Đề có {de.cau.length} câu. {de.thong_bao}</div>
          )}

          {kq && <KetQua kq={kq} onMoBai={onMoBai} dangRut={dang === "rut"} onDeMoi={(a) => void rut(a)} />}

          <div className="ex-wrap">
            {de.cau.map((c) => (
              <Cau key={c.qid} c={c} chon={chon[c.qid] ?? ""} kq={kqTheoQid.get(c.qid)}
                onChon={(v) => setChon((s) => ({ ...s, [c.qid]: v }))} onMoBai={onMoBai} />
            ))}
          </div>

          {loi && <div className="ot-loi">⚠️ {loi}</div>}
          {!kq ? (
            <div className="ot-nop">
              <span className="tnum">Đã trả lời {daTraLoi}/{tuCham}</span>
              <button className="btn btn-primary" type="button" disabled={dang === "nop" || !daTraLoi}
                onClick={() => void nop()}>{dang === "nop" ? "Đang chấm…" : "Nộp bài"}</button>
            </div>
          ) : (
            <div className="ot-nop">
              <span>Chấm ở máy chủ · đáp án chỉ gửi về sau khi nộp.</span>
              <button className="btn" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
                Làm một đề khác
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Kết quả theo YCCĐ + gợi ý (bước ④). */
function KetQua({ kq, onMoBai, onDeMoi, dangRut }: {
  kq: KetQuaCuoiKy;
  onMoBai: (topicId: number, phan?: string) => void;
  onDeMoi: (arIds: string[]) => void;
  dangRut: boolean;
}) {
  const pct = kq.tong ? Math.round((kq.diem * 100) / kq.tong) : 0;
  const yeu = kq.goi_y.ar_ids;
  return (
    <div className="ck-kq">
      <div className="pmach">
        <div className="pmach-h">
          <span className="tt">Kết quả: {kq.diem}/{kq.tong} câu</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
          <span className="num">{pct}%</span>
        </div>
        {kq.khong_cham > 0 && (
          <div className="ck-ghi">{kq.khong_cham} câu không chấm tự động, không tính vào điểm.</div>
        )}
        {/* Chấm theo YÊU CẦU CẦN ĐẠT, đúng thứ tự ma trận — không xếp theo điểm. */}
        <div className="ycd">
          {kq.theo_ycd.map((y) => (
            <div className="ycd-row" key={y.ar_id}>
              <span className={"badge b-" + y.trang}>{y.dung}/{y.tong}</span>
              <span className="ck-ycd-tx">{y.ycd}</span>
            </div>
          ))}
        </div>
      </div>

      {(kq.goi_y.tai_lieu.length > 0 || yeu.length > 0) && (
        <div className="ck-goiy">
          {kq.goi_y.tai_lieu.length > 0 && (
            <>
              <h3><span className="hi">📚</span> Đọc lại trước khi làm tiếp</h3>
              <div className="ck-tl-ds">
                {kq.goi_y.tai_lieu.map((t) => (
                  <button type="button" key={t.topic_id} onClick={() => onMoBai(t.topic_id, t.phan)}>
                    <span className="ic" aria-hidden>📖</span>
                    <span className="tx"><b>{t.don_vi}</b>
                      <span>{t.ycd} · sai câu {t.cau.join(", ")}</span></span>
                    <span className="mui" aria-hidden>↗</span>
                  </button>
                ))}
              </div>
            </>
          )}
          {yeu.length > 0 && (
            <div className="ck-moi">
              <div>
                <b>🔁 Bài làm mới — chỉ {yeu.length} yêu cầu cần đạt còn yếu</b>
                <span>{soCauDeMoi(yeu.length)} câu rút lại từ kho đề, chỉ trong các yêu cầu này.</span>
              </div>
              <button className="btn btn-primary" type="button" disabled={dangRut} onClick={() => onDeMoi(yeu)}>
                {dangRut ? "Đang rút đề…" : "Làm bài mới →"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** "Các lần làm trước" — đề đã nộp mở lại xem kết quả, đề bỏ dở thì làm tiếp. */
export function LichSu({ ds, onMo, tieuDe = "Các lần làm trước" }: {
  ds: DeCuoiKyTomTat[];
  onMo: (x: DeCuoiKyTomTat) => void;
  tieuDe?: string;
}) {
  return (
    <div className="ck-ls">
      <div className="ck-ls-h">🕒 {tieuDe}</div>
      {ds.map((x) => {
        const pct = x.da_nop && x.tong ? Math.round(((x.diem ?? 0) * 100) / x.tong) : null;
        return (
          <button type="button" className="ck-ls-r" key={x.de_id} onClick={() => onMo(x)}>
            {x.da_nop
              ? <span className={"badge " + (x.dat ? "b-dat" : "b-dang")}>{x.diem}/{x.tong}</span>
              : <span className="badge b-chua">Chưa nộp</span>}
            <span className="tx">
              <b>{x.exam ? `Cuối kỳ ${x.exam.replace(/\D/g, "")}` : "Đề cuối kỳ"}
                {x.on_lai && " · ôn lại chỗ yếu"}</b>
              <span className="num">{ngayGio(x.nop_luc ?? x.luc)} · {x.so_cau} câu</span>
            </span>
            <span className="kq">{pct !== null ? `${pct}%` : "Làm tiếp →"}</span>
          </button>
        );
      })}
    </div>
  );
}
