import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, cheDoNhapMa, moBaiMa, moDeCuoiKy, nopDeCuoiKy, rutDeCuoiKy, vaoMaTestbank } from "../api";
import type {
  BaiMa, CauCuoiKy, CheDoNhapMa, DeCuoiKy, DeCuoiKyTomTat, KetQuaCau, KetQuaCuoiKy,
} from "../types";
import { BaiMaView } from "./BaiMaView";
import { DeXuatView } from "./DeXuatView";
import { useLichSuDe } from "./useLichSuDe";

const MUC: Record<string, [string, string]> = {
  B: ["de", "Biết"], H: ["trung_binh", "Hiểu"], V: ["kho", "Vận dụng"],
};
const DANG: Record<string, string> = {
  TN1: "Một đáp án", TNN: "Nhiều đáp án", DS: "Đúng / Sai", DSN: "Điền đáp số", TL: "Tự luận",
};
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
export function Cau({ c, chon, onChon, kq, onMoBai, anXemLai, tuLuanNhap }: {
  c: CauCuoiKy;
  chon: string;
  onChon: (v: string) => void;
  kq?: KetQuaCau;
  onMoBai: (topicId: number, phan?: string) => void;
  /** Ẩn nút "Xem lại bài" — dùng khi câu nằm NGAY trong bài đó (Luyện thêm), nơi đã có
   *  "Đọc lại phần này" riêng. */
  anXemLai?: boolean;
  /** Bài theo mã Testbank: câu tự luận GÕ ĐOẠN CHỮ ngay trong app (Testbank nhận, thầy cô chấm). Đề tự
   *  rút thì tự luận làm ra giấy, không có ô nhập. */
  tuLuanNhap?: boolean;
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
                  <span className="k">{p.nhan ?? p.key}</span>
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
                  <span className="k">{p.nhan ?? p.key}</span>
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

      {tuLuanNhap && c.dang === "TL" && (
        <div className="ck-tl-nhap">
          <textarea value={chon} maxLength={5000} rows={4} placeholder="Gõ bài làm của em ở đây"
            aria-label={`Bài làm câu ${c.stt}`} onChange={(e) => onChon(e.target.value)} />
          <div className="ck-tl">Câu này thầy cô chấm</div>
        </div>
      )}
      {!c.tu_cham && !tuLuanNhap && (
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
          {/* Bài chưa xuất bản thì không có gì để xem lại — nút dẫn tới trang trống (US-27 KB 19). */}
          {!kq!.dung && kq!.topic_id != null && !anXemLai && kq!.bai_xuat_ban !== false && (
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
export function CuoiKyView({ exam, ten, moDe, moLoai, role, onMoBai, onDong }: {
  exam: string;
  ten: string;
  /** Vai: chỉ tài khoản HỌC SINH nhập được mã (US-29 KB 4); thầy cô thấy "giao đề trên Testbank". */
  role?: string;
  /** Mở thẳng đề này (bấm từ Hồ sơ học tập) thay vì màn bắt đầu. `moLoai` = loại bài của dòng đó. */
  moDe?: string;
  moLoai?: string;
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
  const [maNhap, setMaNhap] = useState("");
  // Bài theo mã thầy cô phát trên Testbank (US-29): làm trong BaiMaView, không qua `de` ở trên.
  const [maBai, setMaBai] = useState<BaiMa | null>(null);
  const [cheDo, setCheDo] = useState<CheDoNhapMa | null>(null);
  useEffect(() => {
    if (role === "hoc_sinh") cheDoNhapMa().then(setCheDo).catch(() => setCheDo({ che_do: "tich_hop", url_du_phong: null }));
  }, [role]);
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
  const ls = useLichSuDe(exam, 10, !de && !maBai);

  /** Mở lại một đề: đã nộp -> hiện nguyên kết quả cũ; chưa nộp -> làm tiếp từ nháp. */
  const mo = async (deId: string, onLaiDe = false) => {
    setDang("rut"); setLoi(null);
    try {
      const d = await moDeCuoiKy(deId);
      const k = d.ket_qua ?? null;
      setDe(d); setKq(k); setOnLai(onLaiDe || !!d.on_lai);
      // Đã nộp: dựng lại lựa chọn từ kết quả để các ô hiện đúng em đã chọn gì.
      // Bài theo mã không có nháp (bản demo không lưu lựa chọn dở — US-26 KB 21).
      setChon(k ? Object.fromEntries(k.cau.map((c) => [c.qid, c.chon])) : d.ma ? {} : docNhap(deId));
      veDau();
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không mở được đề, thử lại nhé");
    } finally { setDang(""); }
  };
  useEffect(() => { if (moDe && moLoai !== "testbank") void mo(moDe); }, [moDe]); // eslint-disable-line

  // Lưu nháp khi đang làm (chưa nộp).
  useEffect(() => {
    if (de?.de_id && !de.ma && !kq && Object.keys(chon).length) ghiNhap(de.de_id, chon);
  }, [de, kq, chon]);

  /** Kỳ của đề đang làm: đề theo mã thì lấy theo đề (màn nhập mã không biết trước kỳ). */
  const examDe = de?.exam ?? kq?.goi_y.de_moi.exam ?? exam;

  /** Nhập mã Testbank. Dự phòng (Testbank chưa nối phát đề): mở trang làm bài của Testbank ở tab mới,
   *  mã điền sẵn. Còn lại máy chủ vào thi thay em; sai định dạng thì máy chủ báo, không hỏi Testbank. */
  const vaoMa = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoi(null);
    if (cheDo?.che_do === "du_phong" && cheDo.url_du_phong) {
      const ma = maNhap.replace(/\s+/g, "").toUpperCase();
      if (!/^[A-HJKMNP-Z2-9]{6}$/.test(ma)) { setLoi("Mã gồm 6 chữ và số, em kiểm tra lại nhé"); return; }
      const u = new URL(cheDo.url_du_phong);
      u.searchParams.set("ma", ma);
      window.open(u.toString(), "_blank", "noopener");
      return;
    }
    setDang("rut");
    try {
      setMaBai(await vaoMaTestbank(maNhap));
      veDau();
    } catch (err) {
      setLoi(err instanceof ApiError ? err.message : "Chưa mở được đề, em thử lại sau ít phút nhé");
    } finally { setDang(""); }
  };
  /** Mở lại bài theo mã từ lịch sử. */
  const moMa = async (deId: string) => {
    setDang("rut"); setLoi(null);
    try { setMaBai(await moBaiMa(deId)); veDau(); }
    catch (err) { setLoi(err instanceof ApiError ? err.message : "Chưa mở được bài, em thử lại sau ít phút nhé"); }
    finally { setDang(""); }
  };
  useEffect(() => { if (moDe && moLoai === "testbank") void moMa(moDe); }, [moDe, moLoai]); // eslint-disable-line

  const rut = async () => {
    setDang("rut"); setLoi(null);
    try {
      // Sau bài theo mã: đề tự rút RIÊNG của em, không thuộc mã (US-26 KB 22).
      const d = await rutDeCuoiKy({ exam: examDe, total: 12 });
      setDe(d); setChon({}); setKq(null); setOnLai(false);
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

  if (maBai) {
    return (
      <BaiMaView key={maBai.de_id} bai={maBai} onVe={() => { setMaBai(null); setLoi(null); }}
        onTuSinh={() => { setMaBai(null); void rut(); }} />
    );
  }

  return (
    <div className="lesson ck" ref={dau}>
      <div className="ot-top">
        <span className="badge-hoc">
          {de?.ma ? `🔑 ĐỀ THẦY CÔ GIAO · MÃ ${de.ma}` : `📝 ĐỀ ${onLai ? "ÔN LẠI CHỖ CÒN YẾU" : "CUỐI KỲ"}`}
        </span>
        {de && (
          <button className="ot-dong" type="button" onClick={() => { setDe(null); setKq(null); setLoi(null); }}>
            ☰ Các lần làm</button>
        )}
        <button className="ot-dong ck-ve" type="button" onClick={onDong}>← Về bài học</button>
      </div>
      <h1>{de?.ma ? `Đề cuối học kỳ ${(de.exam ?? "").replace(/\D/g, "") || ""} · Toán 6` : ten}</h1>
      {de?.ma && <p className="ck-giao-ghi">{de.ghi_chu ?? "Đề thầy cô giao"} · cả lớp làm cùng một đề</p>}

      {!de && (
        <div className="ck-mo">
          {/* Hai cách, theo thứ tự (US-29 KB 2): mã thầy cô giao trên Testbank, rồi đề tự sinh. */}
          <div className="ck-cach">
            <section className="ck-the" aria-label="Nhập mã đề thầy cô giao">
              <h2>🔑 Nhập mã đề thầy cô giao</h2>
              <p className="ot-sub">Thầy cô tạo đề trên Testbank và đọc mã 6 chữ và số</p>
              {role === "hoc_sinh" ? (
                <>
                  <form className="ck-ma" onSubmit={(e) => void vaoMa(e)}>
                    <label>
                      <span>Mã đề</span>
                      <input type="text" value={maNhap} maxLength={12} autoComplete="off" autoCapitalize="characters"
                        spellCheck={false} placeholder="Ví dụ: K7M3PX" aria-label="Mã đề thầy cô giao"
                        onChange={(e) => setMaNhap(e.target.value)} />
                    </label>
                    <button className="btn btn-primary" type="submit" disabled={dang === "rut" || !maNhap.trim()}>
                      {dang === "rut" ? "Đang mở đề…" : "Vào làm bài →"}
                    </button>
                  </form>
                  {loi && <div className="ot-loi" role="alert">⚠️ {loi}</div>}
                </>
              ) : (
                <p className="ck-the-gv">Thầy cô giao đề trên Testbank</p>
              )}
            </section>
            <section className="ck-the" aria-label="Làm đề tự sinh">
              <h2>📝 Làm đề tự sinh</h2>
              <p className="ot-sub">12 câu từ kho đề · chấm theo yêu cầu cần đạt</p>
              <button className="btn btn-primary" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
                {dang === "rut" ? "Đang rút đề…" : "Bắt đầu làm đề →"}
              </button>
              {role !== "hoc_sinh" && loi && <div className="ot-loi">⚠️ {loi}</div>}
            </section>
          </div>
          <LichSu ls={ls} onMo={(x) => (x.loai === "testbank" ? void moMa(x.de_id) : void mo(x.de_id, x.on_lai))}
            nhanXoaHet={`Xoá tất cả đề cuối kỳ ${exam.replace(/\D/g, "")}`} />
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

          {kq && <KetQua kq={kq} exam={examDe} onMoBai={onMoBai} onMoDe={(id) => void mo(id, true)} />}

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
              {de.ma ? (
                <button className="btn" type="button" onClick={() => { setDe(null); setKq(null); setLoi(null); }}>
                  Nhập mã khác
                </button>
              ) : (
                <button className="btn" type="button" disabled={dang === "rut"} onClick={() => void rut()}>
                  Làm một đề khác
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Kết quả theo YCCĐ + khối Đề xuất chung (bước ④). */
function KetQua({ kq, exam, onMoBai, onMoDe }: {
  kq: KetQuaCuoiKy;
  exam: string;
  onMoBai: (topicId: number, phan?: string) => void;
  onMoDe: (deId: string) => void;
}) {
  const pct = kq.tong ? Math.round((kq.diem * 100) / kq.tong) : 0;
  return (
    <div className="ck-kq">
      <div className="pmach">
        <div className="pmach-h">
          <span className="tt">Kết quả: {kq.diem}/{kq.tong} câu
            {kq.ma && <b className={"ck-dat " + (kq.dat_yeu_cau ? "ok" : "no")}> · {kq.dat_yeu_cau ? "Đạt" : "Chưa đạt"}</b>}
          </span>
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

      {/* Đọc thêm · Video · Test thêm — một khối cho mọi loại bài (US-27), sau kết quả theo YCCĐ. */}
      <DeXuatView dx={kq.de_xuat} exam={exam} onMoBai={onMoBai} onMoDe={onMoDe} />
    </div>
  );
}

/** "Các lần làm trước" — đề đã nộp mở lại xem kết quả, đề bỏ dở thì làm tiếp.
 *  Mỗi dòng có nút xoá hẳn; cuối danh sách có "Xem thêm" (phân trang) và "Xoá tất cả". */
export function LichSu({ ls, onMo, tieuDe = "Các lần làm trước", nhanXoaHet }: {
  ls: ReturnType<typeof useLichSuDe>;
  onMo: (x: DeCuoiKyTomTat) => void;
  tieuDe?: string;
  nhanXoaHet: string;
}) {
  if (!ls.ds?.length) return ls.loi ? <div className="ot-loi">⚠️ {ls.loi}</div> : null;
  return (
    <div className="ck-ls">
      <div className="ck-ls-h">🕒 {tieuDe}</div>
      {ls.ds.map((x) => {
        const pct = x.da_nop && x.tong ? Math.round(((x.diem ?? 0) * 100) / x.tong) : null;
        const ngung = !!x.da_ngung;
        const theoMa = x.loai === "de_giao" || x.loai === "testbank";
        return (
          <div className="ck-ls-r" key={x.de_id}>
            {/* Hai nút tách rời: nút xoá không được lồng trong nút mở đề (HTML
                không cho button lồng button, và bấm xoá sẽ mở luôn đề). */}
            <button type="button" className={"ck-ls-mo" + (ngung ? " ck-ls-ngung" : "")} disabled={ngung}
              onClick={() => onMo(x)}>
              {x.da_nop
                ? <span className={"badge " + (x.dat ? "b-dat" : "b-dang")}>{Math.round((x.diem ?? 0) * 100) / 100}/{Math.round((x.tong ?? 0) * 100) / 100}</span>
                : <span className="badge b-chua">{x.loai === "testbank" ? "Đang làm" : "Chưa nộp"}</span>}
              <span className="tx">
                <b>{theoMa ? `Thầy cô giao · mã ${x.ma}`
                  : x.exam ? `Cuối kỳ ${x.exam.replace(/\D/g, "")}` : "Đề cuối kỳ"}
                  {x.on_lai && " · ôn lại chỗ yếu"}</b>
                <span className="num">
                  {x.loai === "testbank" && x.tieu_de ? `${x.tieu_de} · ` : ""}
                  {ngung ? "Chưa nộp (đề giao đã ngừng)" : `${ngayGio(x.nop_luc ?? x.luc)}${x.loai === "testbank" ? "" : ` · ${x.so_cau} câu`}`}</span>
              </span>
              <span className="kq">{ngung ? "" : pct !== null ? `${pct}%` : "Làm tiếp →"}</span>
            </button>
            {/* Bài thầy cô giao không có nút xoá: là dữ liệu của giáo viên (US-26 KB 24). */}
            {x.xoa_duoc && (
              <button type="button" className="ck-ls-xoa" title="Xoá hẳn đề này"
                aria-label="Xoá hẳn đề này" onClick={() => void ls.xoa(x)}>🗑</button>
            )}
          </div>
        );
      })}
      {ls.loi && <div className="ot-loi">⚠️ {ls.loi}</div>}
      <div className="ck-ls-f">
        {ls.conNua && (
          <button type="button" className="ck-ls-them" disabled={ls.dangTai}
            onClick={() => void ls.xemThem()}>{ls.dangTai ? "Đang tải…" : "Xem thêm ↓"}</button>
        )}
        {ls.coXoaDuoc && (
          <button type="button" className="ck-ls-xoahet" onClick={() => void ls.xoaHet()}>
            🗑 {nhanXoaHet}</button>
        )}
      </div>
    </div>
  );
}
