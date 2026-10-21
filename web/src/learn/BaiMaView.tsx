import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, luuBaiMa, moBaiMa, nopBaiMa } from "../api";
import type { BaiMa, CauCuoiKy, KetQuaCau, KetQuaCauMa } from "../types";
import { Cau, KetQua } from "./CuoiKyView";

/** Bài theo MÃ THẦY CÔ PHÁT TRÊN TESTBANK (US-29), làm ngay trong app.
 *
 *  Máy chủ learning giữ khoá bài làm và gọi Testbank thay em — trình duyệt chỉ biết `de_id`.
 *  Bài mức 0 (US-29): kết quả chỉ có điểm phần chấm tự động và Đúng / Sai từng câu (Testbank không đưa mã câu
 *  cho đường học sinh nên không có đáp án để tra). Bài mức 1 (US-30): ngay sau nộp hiện giống đề tự sinh — kết
 *  quả theo YCCĐ, khối Đề xuất, "Xem lại bài", đáp án + lời giải + lý do từng phương án. Đáp án lấy từ KHO và
 *  chỉ cho câu đã qua rào đối chiếu với tờ đề; câu bị rào hiện `ghi_chu_cau` thay đáp án, tới khi thầy cô đóng
 *  bài (`giai_doan` 2, đáp án của chính tờ đề). MÁY CHỦ quyết câu nào có đáp án; giao diện chỉ hiện những gì
 *  máy chủ đã gửi, không tự suy ra đáp án ở đâu cả.
 *
 *  Lựa chọn lưu dần lên Testbank; chưa lưu được (mất mạng, Testbank bận) thì GIỮ TRÊN MÁY
 *  (localStorage) và gửi lại khi có mạng — đúng điều em cần để "đừng đóng app" có nghĩa. */

const NHAP = (deId: string) => `ma-nhap:${deId}`;
type Cho = Record<string, { chon: string; seq: number }>;   // qid -> lựa chọn chưa lưu được
const docNhap = (deId: string): Cho => {
  try { return JSON.parse(localStorage.getItem(NHAP(deId)) ?? "{}") ?? {}; } catch { return {}; }
};
const ghiNhap = (deId: string, v: Cho) => {
  try {
    if (Object.keys(v).length) localStorage.setItem(NHAP(deId), JSON.stringify(v));
    else localStorage.removeItem(NHAP(deId));
  } catch { /* localStorage có thể không dùng được (ẩn danh) — bỏ qua */ }
};

const stt = (qid: string) => Number(qid.slice(1));
/** Số thứ tự tăng dần theo thời gian: Testbank bỏ lần gửi cũ tới muộn, và nó phải LỚN hơn mọi
 *  số đã gửi ở những lần mở trước (đếm từ 1 mỗi lần mở sẽ bị bỏ qua). */
let seqCuoi = 0;
const seqMoi = () => (seqCuoi = Math.max(seqCuoi + 1, Date.now()));

const so = (x: number) => String(Math.round(x * 100) / 100).replace(".", ",");

/** Lựa chọn của em thành chữ dễ đọc: "A, C", "Ý a Đúng · Ý b Sai", đáp số, đoạn chữ. */
function chonChu(c: CauCuoiKy | undefined, chon: string): string {
  if (!chon.trim()) return "Em bỏ trống";
  if (c?.dang === "DS") {
    return chon.split(",").map((v, i) => v ? `Ý ${c.phuong_an[i]?.nhan ?? i + 1}: ${v === "Đ" ? "Đúng" : "Sai"}` : "")
      .filter(Boolean).join(" · ") || "Em bỏ trống";
  }
  if (c?.dang === "TNN") return chon.split(",").join(", ");
  return chon;
}

/** Câu có chấm tự động không, đúng không. Bài mức 1 có sẵn `cham_duoc` / `dung` từ máy chủ; bài mức 0 chỉ có
 *  nhãn của Testbank nên suy ra từ đó (tự luận không tính — như `_cham_duoc` ở máy chủ). */
function dangTuCham(c: CauCuoiKy | undefined, k: KetQuaCauMa): { cham_duoc: boolean; dung: boolean } {
  const cham = k.cham_duoc ?? ((c?.dang ?? k.dang) !== "TL"
    && ["DUNG", "SAI", "DUNG_MOT_PHAN"].includes(k.trang_thai));
  return { cham_duoc: cham && (c?.dang ?? k.dang) !== "TL", dung: cham && (k.dung ?? k.trang_thai === "DUNG") };
}

/** Kết quả một câu của bài theo mã -> dạng `KetQuaCau` mà thẻ câu của đề tự sinh đọc. Chưa có đáp án
 *  (giai đoạn 1 / mức 0) thì để trống các trường đáp án và bật `chua_mo_dap_an`: thẻ câu chỉ đánh dấu
 *  phương án em chọn. */
function sangKetQuaCau(c: CauCuoiKy, k: KetQuaCauMa, dt: { cham_duoc: boolean; dung: boolean }): KetQuaCau {
  return {
    stt: c.stt, qid: c.qid, dang: c.dang, ar_id: k.ar_id ?? "", ycd: k.ycd ?? "", topic_id: k.topic_id ?? null,
    don_vi: k.don_vi ?? "", chon: k.chon ?? "", dap_an: k.dap_an ?? "", dap_an_html: k.dap_an_html ?? "",
    cham_duoc: dt.cham_duoc, dung: dt.dung, so_y_dung: k.so_y_dung ?? null, so_y: k.so_y ?? null,
    giai_html: k.giai_html ?? "", ly_do: k.ly_do ?? {}, ly_do_ghi_chu: k.ly_do_ghi_chu,
    bai_xuat_ban: k.bai_xuat_ban, chua_mo_dap_an: k.dap_an === undefined, ghi_chu_cau: k.ghi_chu_cau,
  };
}

/** Câu tự luận (hoặc không chấm tự động được) ở giai đoạn 2: bài làm của em, nhãn chấm như Testbank trả ở
 *  lần learning chép bản đầy đủ, lời giải của tờ đề (nếu có). Không có lý do từng phương án. */
function CauKhongTuCham({ c, k }: { c: CauCuoiKy; k: KetQuaCauMa }) {
  return (
    <div className="ex-card ck-cau ma-kq-cau">
      <div className="ex-head">
        <b>Câu {c.stt}</b>
        <span className="ma-nhan cho">{k.nhan}</span>
        {k.diem != null && k.diem_toi_da != null && <span className="ck-dang">{so(k.diem)}/{so(k.diem_toi_da)} điểm</span>}
      </div>
      <div className="ex-q ck-q" dangerouslySetInnerHTML={{ __html: c.de_html }} />
      <div className="ma-chon">Bài làm của em: <b>{chonChu(c, k.chon ?? "")}</b></div>
      {k.dap_an_html && <div className="ma-chon">Đáp án: <b dangerouslySetInnerHTML={{ __html: k.dap_an_html }} /></div>}
      {k.giai_html && <div className="ex-giai"><b>Lời giải:</b> <span dangerouslySetInnerHTML={{ __html: k.giai_html }} /></div>}
      {k.ghi_chu_cau && <div className="ck-tl">{k.ghi_chu_cau}</div>}
    </div>
  );
}

export function BaiMaView({ bai: ban, exam, onVe, onTuSinh, onMoBai, onMoDe }: {
  bai: BaiMa;
  /** Kỳ của màn đề cuối kỳ — "Test thêm" ghi vào đúng kỳ. */
  exam: string;
  /** Về màn đề cuối kỳ (đóng bài). */
  onVe: () => void;
  /** "Làm đề tự sinh để luyện thêm". */
  onTuSinh: () => void;
  /** "Xem lại bài" / bài học trong khối Đề xuất. */
  onMoBai: (topicId: number, phan?: string) => void;
  /** Mở bài "Test thêm" vừa tạo. */
  onMoDe: (deId: string) => void;
}) {
  const [bai, setBai] = useState<BaiMa>(ban);
  const [chon, setChon] = useState<Record<string, string>>(() => {
    const nhap = docNhap(ban.de_id);
    return { ...ban.tra_loi, ...Object.fromEntries(Object.entries(nhap).map(([k, v]) => [k, v.chon])) };
  });
  const [luu, setLuu] = useState<"" | "dang" | "da" | "loi">("");
  const [loi, setLoi] = useState<string | null>(null);
  const [dangNop, setDangNop] = useState(false);
  const [conLai, setConLai] = useState<number | null>(null);
  const [hetGio, setHetGio] = useState(false);
  const dau = useRef<HTMLDivElement>(null);

  const cho = useRef<Cho>(docNhap(ban.de_id));
  const dangGui = useRef(false);
  const hen = useRef<number | undefined>(undefined);
  const daNop = bai.trang_thai === "DA_NOP";
  const deId = bai.de_id;

  const nhan = useCallback((b: BaiMa) => {
    setBai(b); cho.current = {}; ghiNhap(b.de_id, {});
    setLoi(null); setLuu(""); setHetGio(false);
    window.setTimeout(() => dau.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }, []);

  /** Gửi các lựa chọn còn chờ. Lỗi thì giữ nguyên trong `cho` và thử lại sau 5 giây. */
  const gui = useCallback(async () => {
    if (dangGui.current || !Object.keys(cho.current).length) return;
    dangGui.current = true; setLuu("dang");
    const lo = Object.entries(cho.current).map(([q, v]) => ({ stt: stt(q), chon: v.chon, seq: v.seq }));
    try {
      const r = await luuBaiMa(deId, lo);
      if (r.da_nop) { nhan(r.bai); return; }
      // Chỉ bỏ khỏi hàng chờ những gì CHƯA đổi từ lúc gửi (em có thể vừa sửa tiếp).
      for (const x of lo) if (cho.current[`c${x.stt}`]?.seq === x.seq) delete cho.current[`c${x.stt}`];
      ghiNhap(deId, cho.current);
      setLuu(Object.keys(cho.current).length ? "dang" : "da");
      if (Object.keys(cho.current).length) hen.current = window.setTimeout(() => void gui(), 300);
    } catch {
      setLuu("loi");
      hen.current = window.setTimeout(() => void gui(), 5000);
    } finally { dangGui.current = false; }
  }, [deId, nhan]);

  const doi = (qid: string, v: string) => {
    setChon((s) => ({ ...s, [qid]: v }));
    cho.current[qid] = { chon: v, seq: seqMoi() };
    ghiNhap(deId, cho.current);
    window.clearTimeout(hen.current);
    hen.current = window.setTimeout(() => void gui(), 500);
  };

  // Còn lựa chọn giữ từ lần trước (đóng app giữa chừng) -> gửi ngay; có mạng lại -> gửi lại.
  useEffect(() => {
    if (daNop) return;
    void gui();
    const online = () => void gui();
    window.addEventListener("online", online);
    return () => { window.removeEventListener("online", online); window.clearTimeout(hen.current); };
  }, [daNop, gui]);

  // Đồng hồ đếm ngược theo GIỜ MÁY CHỦ: hạn - giờ máy chủ lúc nhận, trừ thời gian đã trôi trên máy em.
  const nhanLuc = useRef(Date.now());
  useEffect(() => { nhanLuc.current = Date.now(); }, [bai]);
  const conLaiMs = useMemo(() => (bai.han_nop_luc && bai.gio_may_chu && !daNop
    ? Date.parse(bai.han_nop_luc) - Date.parse(bai.gio_may_chu) : null), [bai, daNop]);
  useEffect(() => {
    if (conLaiMs == null) { setConLai(null); return; }
    const tick = () => setConLai(Math.max(0, conLaiMs - (Date.now() - nhanLuc.current)));
    tick();
    const t = window.setInterval(tick, 1000);
    return () => window.clearInterval(t);
  }, [conLaiMs]);

  // Hết giờ: gửi nốt rồi hỏi Testbank (nó tự nộp bài khi có ai chạm vào) tới khi có kết quả.
  // Cờ bằng ref, KHÔNG dùng cleanup của effect: `setHetGio` làm effect chạy lại và cleanup sẽ cắt
  // ngang vòng hỏi vừa bắt đầu.
  const daBatDau = useRef(false);
  useEffect(() => {
    if (conLai !== 0 || daNop || daBatDau.current) return;
    daBatDau.current = true;
    setHetGio(true);
    (async () => {
      await gui();
      for (let i = 0; i < 20; i++) {
        try {
          const b = await moBaiMa(deId);
          if (b.trang_thai === "DA_NOP") { nhan(b); return; }
        } catch { /* thử lại */ }
        await new Promise((r) => setTimeout(r, 3000));
      }
      daBatDau.current = false;
      setLoi("Chưa lấy được kết quả, em bấm \"Nộp bài\" hoặc mở lại bài sau ít phút nhé");
    })();
  }, [conLai, daNop, gui, deId, nhan]);

  const nop = async () => {
    setDangNop(true); setLoi(null);
    try {
      // Gửi kèm TOÀN BỘ lựa chọn em đang giữ: chắc chắn đủ kể cả khi lần lưu cuối chưa tới nơi.
      const tatCa = Object.entries(chon).map(([q, v]) => ({
        stt: stt(q), chon: v, seq: cho.current[q]?.seq ?? seqMoi() }));
      nhan(await nopBaiMa(deId, tatCa));
    } catch (e) {
      // Lựa chọn vẫn nằm trên máy; em bấm Nộp lại sau.
      setLoi(e instanceof ApiError ? e.message
        : "Chưa gửi được bài, em đừng đóng app, bấm Nộp lại sau ít phút");
    } finally { setDangNop(false); }
  };

  const daTraLoi = bai.cau.filter((c) => (chon[c.qid] ?? "").trim()).length;
  const phut = conLai == null ? "" : `${Math.floor(conLai / 60000)}:${String(Math.floor(conLai / 1000) % 60).padStart(2, "0")}`;
  const kq = bai.ket_qua;
  const theoStt = new Map<number, KetQuaCauMa>((kq?.cau ?? []).map((k) => [k.stt, k]));
  // Điểm "x/y câu" của khung kết quả = số câu chấm tự động đúng / số câu chấm tự động (như đề tự sinh);
  // điểm Testbank (có thể lẻ) nằm ở dòng ghi chú bên dưới.
  const dts = (kq?.cau ?? []).map((k) => dangTuCham(bai.cau.find((c) => c.stt === k.stt), k));
  const tomTat = kq && {
    diem: dts.filter((d) => d.dung).length, tong: dts.filter((d) => d.cham_duoc).length,
    khong_cham: dts.filter((d) => !d.cham_duoc).length, theo_ycd: kq.theo_ycd ?? [], de_xuat: kq.de_xuat,
  };

  return (
    <div className="lesson ck" ref={dau}>
      <div className="ot-top">
        <span className="badge-hoc">🔑 {bai.nhan.toUpperCase()}</span>
        <button className="ot-dong ck-ve" type="button" onClick={onVe}>← Các cách làm đề</button>
      </div>
      <h1>{bai.tieu_de || "Đề thầy cô giao"}</h1>
      <p className="ck-giao-ghi">{bai.nhan}</p>

      {!daNop && (
        <div className="ma-thanh" role="status">
          {conLai != null && <span className={"ma-dongho" + (conLai < 5 * 60000 ? " gap" : "")}>⏱ Còn {phut}</span>}
          <span className={"ma-luu " + luu}>
            {luu === "dang" ? "Đang lưu…" : luu === "da" ? "Đã lưu" : luu === "loi" ? "Chưa lưu được, đang thử lại" : ""}
          </span>
        </div>
      )}
      {hetGio && !daNop && <div className="ck-thieu" role="status">⏱ Hết giờ, đang nộp bài của em…</div>}

      {/* Cùng khung, cùng thứ tự khối, cùng thẻ câu với đề tự sinh (CuoiKyView) — chỉ khác những gì
          máy chủ CHƯA gửi: giai đoạn 1 không có đáp án / lời giải / lý do, bài mức 0 không có YCCĐ. */}
      {daNop && kq && (
        <KetQua kq={tomTat!} exam={exam} onMoBai={onMoBai} onMoDe={onMoDe}
          thongBao={(bai.thong_bao || bai.ghi_chu.length > 0) && (
            <>
              {bai.thong_bao && <div className="ck-thieu" role="status">ℹ️ {bai.thong_bao}</div>}
              {bai.ghi_chu.map((g) => <div className="ck-thieu" role="status" key={g}>ℹ️ {g}</div>)}
            </>
          )}
          ghiChu={(
            <>
              <div className="ck-ghi">Điểm phần chấm tự động: {so(kq.diem)}/{so(kq.tong)}</div>
              {kq.so_cau_cho_cham > 0 && <div className="ck-ghi">{kq.so_cau_cho_cham} câu thầy cô chấm sau</div>}
              {bai.giai_doan === 0 && bai.ghi_chu.length === 0 && (
                <div className="ck-ghi">Thầy cô sẽ chữa bài trên lớp.</div>
              )}
            </>
          )} />
      )}

      <div className="ex-wrap">
        {bai.cau.map((c) => {
          if (!daNop) {
            return (
              <Cau key={c.qid} c={c} chon={chon[c.qid] ?? ""} tuLuanNhap
                onChon={(v) => doi(c.qid, v)} onMoBai={() => undefined} />
            );
          }
          const k = theoStt.get(c.stt);
          if (!k) return <Cau key={c.qid} c={c} chon="" onChon={() => undefined} onMoBai={onMoBai} />;
          const dt = dangTuCham(c, k);
          if (!dt.cham_duoc) return <CauKhongTuCham key={c.qid} c={c} k={k} />;
          return (
            <Cau key={c.qid} c={{ ...c, muc_do: k.muc_do || c.muc_do, don_vi: k.don_vi || c.don_vi, ycd: k.ycd || c.ycd }}
              chon={k.chon ?? ""} kq={sangKetQuaCau(c, k, dt)} onChon={() => undefined} onMoBai={onMoBai} />
          );
        })}
      </div>

      {loi && <div className="ot-loi" role="alert">⚠️ {loi}</div>}
      {!daNop && (
        <div className="ot-nop">
          <span className="tnum">Đã trả lời {daTraLoi}/{bai.cau.length}</span>
          <button className="btn btn-primary" type="button" disabled={dangNop || hetGio}
            onClick={() => void nop()}>{dangNop ? "Đang nộp…" : "Nộp bài"}</button>
        </div>
      )}
      {daNop && kq && (
        <div className="ot-nop">
          <span>{bai.giai_doan === 2 || bai.co_giai_thich ? "Chấm ở máy chủ · đáp án chỉ gửi về sau khi nộp." : ""}</span>
          <button className="btn" type="button" onClick={onTuSinh}>Làm đề tự sinh để luyện thêm</button>
        </div>
      )}
    </div>
  );
}
