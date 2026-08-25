import { useEffect, useRef, useState } from "react";
import {
  ApiError, cmsDocThuSach, cmsDsJobSach, cmsGanSoTrang, cmsJobSach, cmsKhoSgk,
  cmsLenhJobSach, cmsNapSach, cmsNapTepSach, cmsSoatSach,
} from "../api";
import type { BookJob, DocThu, KhoSgk, SoatSach } from "../types";
import { DaiTrang, daiTuJob, daiTuSoat } from "./DaiTrang";

const MON = [{ v: "toan", n: "Toán" }, { v: "tieng_anh", n: "Tiếng Anh" }];
const KHOI = ["lop_6", "lop_7", "lop_8", "lop_9"];
const BUOC: Record<string, string> = {
  doc: "Đang đọc trang", cat_doan: "Đang cắt đoạn", ghi_kho: "Đang ghi vào kho",
};
const TT: Record<string, [string, string]> = {
  cho: ["p-nhap", "Chờ chạy"], dang: ["p-duyet", "Đang nạp"],
  tam_dung: ["p-nhap", "Tạm dừng"], xong: ["p-xong", "Trong kho"], loi: ["p-loi", "Lỗi"],
};
const LY_DO: Record<string, string> = {
  chua_gan_bai: "chưa gán được “Bài mấy” — đoạn mất ngữ cảnh, nên đọc lại",
  // Không phải OCR sai: nạp lẻ một dải trang thì forward-fill thiếu ngữ cảnh
  // các trang phía trước. Nạp cả tập là hết, không cần soát tay.
  thieu_ngu_canh: "thiếu ngữ cảnh vì nạp lẻ — nạp cả tập sẽ tự gán được",
  it_chu: "rất ít chữ — có thể là trang hình hoặc ảnh mờ",
  loi_doc: "đọc lỗi — cần đọc lại",
};
// ~9 giây/trang đo trên pilot Toán 6. Chỉ để ước lượng, không phải cam kết.
const GIAY_MOI_TRANG = 9;
const CHU_GIAI = [
  { tt: "xong" as const, nhan: "đã đọc" },
  { tt: "dang" as const, nhan: "đang đọc" },
  { tt: "loi" as const, nhan: "đọc lỗi" },
  { tt: "thieu" as const, nhan: "khuyết trang" },
  { tt: "cho" as const, nhan: "chưa tới" },
];

function phut(n: number): string {
  const p = Math.round((n * GIAY_MOI_TRANG) / 60);
  return p < 1 ? "dưới 1 phút" : `khoảng ${p} phút`;
}

/** Nạp sách bằng AI (REQ §2.4) — 4 màn: chọn tệp → đọc thử → đang nạp → soát.
 *
 *  Bốn ràng buộc thật định hình màn này: một tập là 151 ẢNH TRANG (không phải
 *  một tệp); mỗi trang là MỘT lần gọi vision LLM (cả tập ~22 phút); số trang lấy
 *  từ TÊN TỆP nên sai thứ tự là dẫn nguồn trỏ sai bài; và cache OCR làm việc nạp
 *  tiếp gần như miễn phí. Vì vậy có hai chốt chặn trước khi tiêu tiền: soát số
 *  trang, rồi đọc thử vài trang. */
export function KhoSgkView({ toast }: { toast: (m: string) => void }) {
  const [mon, setMon] = useState("toan");
  const [khoi, setKhoi] = useState("lop_6");
  const [tap, setTap] = useState(1);
  const [sach, setSach] = useState("cung_kham_pha_tap_1");

  const [kho, setKho] = useState<KhoSgk | null>(null);
  const [d, setD] = useState<SoatSach | null>(null);
  const [thu, setThu] = useState<DocThu | null>(null);
  const [xemTrang, setXemTrang] = useState(0);
  const [jobs, setJobs] = useState<BookJob[]>([]);
  const [job, setJob] = useState<BookJob | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "tep" | "thu" | "nap" | "lenh">("");
  const [keo, setKeo] = useState(false);
  const [ganSo, setGanSo] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  const loi = (e: unknown, mac: string) =>
    setErr(e instanceof ApiError ? e.message : mac);

  const taiSoat = () => {
    cmsSoatSach(mon, khoi, tap).then(setD).catch((e) => loi(e, "Không soát được thư mục sách"));
  };
  useEffect(() => {
    setD(null); setThu(null); setErr(null);
    taiSoat();
  }, [mon, khoi, tap]);
  useEffect(() => {
    cmsKhoSgk().then(setKho).catch(() => setKho(null));
    cmsDsJobSach().then((r) => {
      setJobs(r.jobs);
      // Có việc đang chạy -> mở luôn màn tiến trình, không bắt người soạn đi tìm.
      setJob(r.jobs.find((j) => j.trang_thai === "dang" || j.trang_thai === "cho") ?? null);
    }).catch(() => setJobs([]));
  }, []);

  // Đang chạy thì hỏi lại mỗi 3 giây. Không dùng WebSocket: một job chạy 20 phút,
  // 3 giây/lần là 400 request — rẻ hơn nhiều so với dựng kênh realtime riêng.
  useEffect(() => {
    if (!job || (job.trang_thai !== "dang" && job.trang_thai !== "cho")) return;
    const t = window.setInterval(() => {
      cmsJobSach(job.id).then((j) => {
        setJob(j);
        if (j.trang_thai === "xong") { toast("Nạp sách xong"); taiSoat(); cmsKhoSgk().then(setKho); }
      }).catch(() => { /* mạng chớp nháy — vòng sau thử lại */ });
    }, 3000);
    return () => window.clearInterval(t);
  }, [job?.id, job?.trang_thai]);

  const napTep = async (fs: FileList | File[] | null) => {
    const ds = Array.from(fs ?? []);
    if (!ds.length) return;
    setBusy("tep"); setErr(null);
    try {
      const r = await cmsNapTepSach(mon, khoi, tap, ds);
      setD(r);
      const n = (r.da_luu ?? []).length;
      toast(`Đã nhận ${n} trang`
        + ((r.cho_gan_moi ?? []).length ? ` · ${r.cho_gan_moi!.length} tệp chờ gán số` : "")
        + ((r.ghi_de ?? []).length ? ` · ghi đè ${r.ghi_de!.length} trang cũ` : ""));
    } catch (e) { loi(e, "Không tải được tệp"); }
    finally { setBusy(""); if (fileRef.current) fileRef.current.value = ""; }
  };

  const gan = async (ten: string, so: number | null) => {
    setErr(null);
    try { setD(await cmsGanSoTrang(mon, khoi, tap, ten, so)); }
    catch (e) { loi(e, "Không gán được số trang"); }
  };

  const docThu = async (lamLai = false) => {
    setBusy("thu"); setErr(null);
    try {
      setThu(await cmsDocThuSach(mon, khoi, tap, [], lamLai));
      setXemTrang(0);
    } catch (e) { loi(e, "Không đọc thử được"); }
    finally { setBusy(""); }
  };

  const nap = async () => {
    setBusy("nap"); setErr(null);
    try {
      const j = await cmsNapSach(mon, khoi, tap, sach.trim());
      setJob(j); setJobs((v) => [j, ...v]);
      toast(j.canh_bao ?? `Đã bắt đầu nạp ${j.tong} trang — chạy nền`);
    } catch (e) { loi(e, "Không tạo được việc nạp"); }
    finally { setBusy(""); }
  };

  const lenh = async (l: "tam_dung" | "tiep" | "huy") => {
    if (!job) return;
    setBusy("lenh"); setErr(null);
    try { setJob(await cmsLenhJobSach(job.id, l)); }
    catch (e) { loi(e, "Không gửi được lệnh"); }
    finally { setBusy(""); }
  };

  // Chỉ "dang" mới CHẶN nút nạp. "cho" là đang đợi worker nhận — worker chết thì
  // việc nằm đó mãi, chặn luôn nút nạp thì người soạn bị kẹt không đường ra.
  const dangChay = job?.trang_thai === "dang";
  const dangCho = job?.trang_thai === "cho";
  const conLai = job ? job.tong - job.da_xong : 0;
  const moi = d ? d.trang.filter((n) => !d.da_ocr.includes(n)).length : 0;

  return (
    <>
      <div className="page-head">
        <div><h1>Nạp sách bằng AI</h1>
          <div className="ps">Ảnh trang sách → OCR → cắt đoạn → kho SGK.
            Mỗi trang là một lần gọi AI, nên đọc thử vài trang trước khi nạp cả tập.</div></div>
      </div>

      {kho && (
        <div className="kpis">
          <div className="kpi"><div className="ic ic-total">📚</div>
            <div className="v tnum">{kho.kpi.so_sach}</div><div className="l">Sách trong kho</div></div>
          <div className="kpi"><div className="ic ic-ai">📄</div>
            <div className="v tnum">{kho.kpi.so_trang}</div><div className="l">Trang đã đọc</div></div>
          <div className="kpi"><div className="ic ic-ok">🧩</div>
            <div className="v tnum">{kho.kpi.so_doan}</div><div className="l">Đoạn tri thức</div></div>
          <div className="kpi"><div className="ic ic-warn">🔖</div>
            <div className="v tnum">{kho.kpi.pt_dan_nguon}%</div><div className="l">Có dẫn nguồn</div></div>
        </div>
      )}
      {kho?.kho_loi && (
        <div className="warn-box" style={{ marginBottom: 14 }}>
          ⚠️ Không nối được kho tri thức (Qdrant). Số đoạn/trang hiện 0 vì
          <b> chưa đọc được</b>, không phải vì kho rỗng — kiểm tra Qdrant.
        </div>
      )}
      {kho?.kho_trong && (
        <div className="hop-tin" style={{ marginBottom: 14 }}>
          <span aria-hidden>📭</span>
          <div><b>Kho tri thức còn rỗng.</b> Qdrant chạy bình thường nhưng chưa có
            sách nào được nạp vào — tải ảnh trang lên rồi bấm “Nạp cả tập”.</div>
        </div>
      )}

      <div className="catalog-bar" style={{ marginBottom: 14 }}>
        <label className="cb"><span>Môn học</span>
          <select value={mon} onChange={(e) => setMon(e.target.value)}>
            {MON.map((m) => <option key={m.v} value={m.v}>{m.n}</option>)}
          </select></label>
        <label className="cb"><span>Khối</span>
          <select value={khoi} onChange={(e) => setKhoi(e.target.value)}>
            {KHOI.map((k) => <option key={k} value={k}>{k.replace("lop_", "Lớp ")}</option>)}
          </select></label>
        <label className="cb"><span>Tập</span>
          <select value={tap} onChange={(e) => setTap(+e.target.value)}>
            {[1, 2].map((t) => <option key={t} value={t}>Tập {t}</option>)}
          </select></label>
        <label className="cb" style={{ flex: 1, minWidth: 190 }}><span>Mã sách</span>
          <input type="text" value={sach} onChange={(e) => setSach(e.target.value)}
            placeholder="cung_kham_pha_tap_1" /></label>
      </div>

      {err && <div className="warn-box" style={{ marginBottom: 14 }}>⚠️ {err}</div>}

      {/* ═══ MÀN 3: đang nạp — ưu tiên hiện trước, đó là việc đang diễn ra ═══ */}
      {job && job.trang_thai !== "xong" && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="panel-h">
            <h3>{MON.find((m) => m.v === job.mon)?.n} · {job.khoi.replace("lop_", "Lớp ")} · Tập {job.tap}</h3>
            <span className={"pill " + TT[job.trang_thai][0]}>{TT[job.trang_thai][1]}</span>
          </div>
          <div style={{ padding: "13px 14px 0" }}>
            <div className="ns-so tnum">{job.da_xong}<small> / {job.tong} trang</small></div>
            <div className="ns-mo">
              {dangChay ? BUOC[job.buoc]
                : dangCho ? "Đang đợi worker nhận việc" : TT[job.trang_thai][1]}
              {dangChay && conLai > 0 && ` · còn ${phut(conLai)}`}
              {job.trang_loi.length > 0 && ` · ${job.trang_loi.length} trang đọc lỗi`}
            </div>
            <div className="ns-track">
              <i style={{ width: `${job.tong ? (job.da_xong / job.tong) * 100 : 0}%` }} />
            </div>
          </div>
          <DaiTrang o={daiTuJob(job)} chuGiai={CHU_GIAI} />
          <div style={{ padding: "0 14px 14px" }}>
            {job.loi && <div className="warn-box" style={{ marginBottom: 10 }}>⚠️ {job.loi}</div>}
            <div className="hop-tin">
              <span aria-hidden>💾</span>
              <div><b>Trang đã đọc thì không đọc lại.</b> Mỗi trang xong được ghi cache
                ngay, nên tạm dừng rồi chạy tiếp chỉ tốn từ trang đang dở.</div>
            </div>
            <div className="ns-hang">
              {dangChay || dangCho
                ? <>
                    <button className="btn2" type="button" disabled={busy !== ""}
                      onClick={() => lenh("tam_dung")}>⏸ Tạm dừng</button>
                    <button className="btn2" type="button" disabled={busy !== ""}
                      onClick={() => lenh("huy")}>
                      ✕ Huỷ, giữ {job.da_xong} trang đã đọc</button>
                  </>
                : <button className="btn2" type="button" disabled={busy !== ""}
                    onClick={() => lenh("tiep")}>▶ Nạp tiếp từ trang {job.da_xong + 1}</button>}
              <span className="ns-ghi">Chạy nền — đóng tab vẫn tiếp tục.</span>
            </div>
          </div>
        </div>
      )}

      <div className="grid2" style={{ alignItems: "start" }}>
        <div>
          {/* ═══ MÀN 1: chọn tệp ═══ */}
          <div className={"dz" + (keo ? " keo" : "")}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setKeo(true); }}
            onDragLeave={() => setKeo(false)}
            onDrop={(e) => { e.preventDefault(); setKeo(false); void napTep(e.dataTransfer.files); }}>
            <input ref={fileRef} type="file" multiple hidden
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => void napTep(e.target.files)} />
            <div className="dz-mo">
              <span className="em" aria-hidden>📚</span>
              <b>{busy === "tep" ? "Đang tải ảnh trang…" : "Kéo cả quyển sách vào đây"}</b>
              <span>hoặc bấm để chọn nhiều ảnh trang</span>
              <small>PNG · JPG · WEBP — tên tệp nên là số trang: <code>045.png</code></small>
            </div>
          </div>

          {d && d.trang.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>Đã có {d.trang.length} ảnh trang</h3>
                <span className="vz-ghi">số trang đọc từ tên tệp</span></div>
              <DaiTrang o={daiTuSoat(d)} chuGiai={CHU_GIAI} />
              {d.thieu.length > 0 && (
                <div style={{ padding: "0 14px 12px" }}>
                  <div className="warn-box">
                    ⚠️ Khuyết {d.thieu.length} trang ở giữa: {d.thieu.slice(0, 12).join(", ")}
                    {d.thieu.length > 12 && "…"} — gần như chắc chắn bỏ sót khi chụp.
                  </div>
                </div>
              )}
            </div>
          )}

          {d && d.cho_gan.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>{d.cho_gan.length} tệp chưa rõ số trang</h3>
                <span className="vz-ghi">gán tay hoặc bỏ</span></div>
              <div style={{ padding: "6px 14px 12px" }}>
                <div className="hop-tin" style={{ marginBottom: 9 }}>
                  <span aria-hidden>ℹ️</span>
                  <div>Cố ý không đoán bừa: <code>Scan (2).png</code> có số 2 trong tên
                    nhưng đoán sai là <b>ghi đè trang 2 thật</b> của quyển sách.</div>
                </div>
                {d.cho_gan.map((t) => (
                  <div className="tep" key={t.ten}>
                    <span className="tep-ic" aria-hidden>🖼️</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="u-name">{t.ten}</div>
                      <div className="u-mach">{t.kb} KB</div>
                    </div>
                    <input className="ns-oso" type="text" inputMode="numeric" placeholder="trang?"
                      value={ganSo[t.ten] ?? ""}
                      onChange={(e) => setGanSo((g) => ({ ...g, [t.ten]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key !== "Enter") return;
                        const n = Number(ganSo[t.ten]);
                        if (n >= 1) void gan(t.ten, n);
                      }} />
                    <button className="btn2 nho" type="button"
                      disabled={!(Number(ganSo[t.ten]) >= 1)}
                      onClick={() => void gan(t.ten, Number(ganSo[t.ten]))}>Gán</button>
                    <button className="rm" type="button" title="Bỏ tệp này"
                      onClick={() => void gan(t.ten, null)}>×</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ═══ MÀN 2: đọc thử ═══ */}
          {thu && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>Kết quả đọc thử</h3>
                <span className="vz-ghi">trang {thu.trang.map((t) => t.so).join(" · ")}</span></div>
              <div className="ns-tab">
                {thu.trang.map((t, i) => (
                  <button key={t.so} type="button"
                    className={"ns-tabb" + (i === xemTrang ? " dang" : "")}
                    onClick={() => setXemTrang(i)}>
                    Trang {t.so}
                    {t.loi ? " ⛔" : t.it_chu ? " ⚠️" : t.co_cong_thuc ? " ƒ" : ""}
                  </button>
                ))}
              </div>
              {(() => {
                const t = thu.trang[xemTrang];
                if (!t) return null;
                if (t.loi) return <div className="warn-box" style={{ margin: 14 }}>⛔ {t.loi}</div>;
                return (
                  <div className="ns-ocr">
                    <div>
                      <div className="ns-nhan">
                        MARKDOWN AI ĐỌC ĐƯỢC · {t.chu} ký tự
                        {t.co_cong_thuc ? " · có công thức" : " · không thấy công thức"}
                        {t.co_bai && " · mở đầu một Bài"}
                      </div>
                      <pre className="ns-md">{t.md}</pre>
                    </div>
                  </div>
                );
              })()}
              <div style={{ padding: "0 14px 14px" }}>
                {/* Chỉ số chính là CÔNG THỨC, không phải “Bài mấy”: đo trên sách
                    thật thì hầu hết trang giữa bài không có heading “Bài N”, lấy
                    nó làm thước đo là báo động sai suốt. OCR sách Toán vỡ ở công
                    thức chứ không vỡ ở chữ. */}
                <div className={thu.so_cong_thuc === thu.so_trang - thu.so_loi
                                && !thu.so_it_chu ? "hop-ok" : "hop-canh"}>
                  <span aria-hidden>🔎</span>
                  <div>
                    <b>Đọc được công thức ở {thu.so_cong_thuc}/{thu.so_trang} trang thử.</b>
                    {" "}Với sách Toán, OCR vỡ ở công thức chứ không vỡ ở chữ — xem kỹ
                    markdown bên trên, thấy <code>2³·5</code> thành <code>235</code> là phải
                    đổi nguồn ảnh trước khi nạp cả tập.
                    {thu.so_it_chu > 0 && <> {thu.so_it_chu} trang rất ít chữ (ảnh mờ?).</>}
                    {thu.so_loi > 0 && <> {thu.so_loi} trang đọc lỗi.</>}
                  </div>
                </div>
                <div className="ns-hang">
                  <button className="btn2" type="button" disabled={busy !== ""}
                    onClick={() => void docThu(true)}>🔁 Đọc lại (bỏ cache)</button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="panel">
            <div className="panel-h"><h3>Trước khi nạp cả tập</h3></div>
            <div style={{ padding: 14 }}>
              {!d || !d.trang.length ? (
                <div className="viz-trong">Chưa có ảnh trang nào cho tập này.</div>
              ) : (
                <>
                  <div className="hop-tin">
                    <span aria-hidden>💰</span>
                    <div>
                      {moi > 0
                        ? <><b>{moi} trang chưa đọc × 1 lượt gọi AI ≈ {phut(moi)}.</b>
                            {d.da_ocr.length > 0 && <> {d.da_ocr.length} trang đã có cache
                              nên gần như miễn phí.</>}</>
                        : <><b>Cả {d.trang.length} trang đã có cache OCR.</b> Nạp lại gần như
                            không tốn gì — chỉ cắt đoạn và ghi vào kho.</>}
                      {" "}OCR sai công thức thì cả quyển phải làm lại — nên đọc thử trước.</div>
                  </div>
                  <button className="btn2 full" type="button" disabled={busy !== ""}
                    onClick={() => void docThu(false)}>
                    {busy === "thu" ? "Đang đọc thử…"
                      : `🔍 Đọc thử ${d.goi_y_thu.length} trang (${d.goi_y_thu.join(", ")})`}
                  </button>
                  <button className="btn full" type="button"
                    disabled={busy !== "" || !sach.trim() || dangChay || dangCho}
                    onClick={() => void nap()}>
                    {busy === "nap" ? "Đang tạo việc…"
                      : dangChay ? "Đang có việc chạy…"
                      : dangCho ? "Có việc đang đợi worker…"
                      : `▶ Nạp cả tập (${d.trang.length} trang)`}
                  </button>
                  {!sach.trim() && <div className="ns-ghi" style={{ marginTop: 8 }}>
                    Nhập mã sách ở trên — nó đi vào dẫn nguồn của từng đoạn.</div>}
                </>
              )}
            </div>
          </div>

          {/* ═══ MÀN 4: soát trang đáng ngờ ═══ */}
          {job?.trang_thai === "xong" && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>Kết quả nạp</h3>
                <span className="pill p-xong">Trong kho</span></div>
              <div style={{ padding: "6px 14px 12px" }}>
                <div className="tep"><div style={{ flex: 1 }}>
                  <div className="u-name">Trang vào kho</div>
                  <div className="u-mach">{job.trang_loi.length} trang đọc lỗi bị bỏ</div></div>
                  <div className="ns-so nho tnum">{job.da_xong}</div></div>
                <div className="tep"><div style={{ flex: 1 }}>
                  <div className="u-name">Đoạn tri thức</div>
                  <div className="u-mach">cắt theo bài</div></div>
                  <div className="ns-so nho tnum">{job.so_doan}</div></div>
                <div className="tep"><div style={{ flex: 1 }}>
                  <div className="u-name">Gán được chương/bài</div>
                  <div className="u-mach">{job.da_xong - job.so_trang_co_bai} trang chưa gán</div></div>
                  <div className="ns-so nho tnum" style={{
                    color: job.so_trang_co_bai === job.da_xong ? "var(--ok)" : "var(--warn)" }}>
                    {job.da_xong ? Math.round((job.so_trang_co_bai / job.da_xong) * 100) : 0}%
                  </div></div>
                <div className="hop-ok" style={{ marginTop: 11 }}>
                  <span aria-hidden>✅</span>
                  <div><b>Kho đã dùng được.</b> “Gợi ý AI” trong trình soạn bài giờ tra được
                    quyển này và dẫn đúng số trang.</div>
                </div>
              </div>
            </div>
          )}

          {job && job.trang_soat.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>{job.trang_soat.length} trang nên xem lại</h3>
                <span className="vz-ghi">trong {job.da_xong} trang</span></div>
              <div style={{ padding: "6px 14px 12px" }}>
                {job.trang_soat.slice(0, 30).map((t) => (
                  <div className="tep" key={`${t.so}-${t.ly_do}`}>
                    <span className="tep-ic" aria-hidden>
                      {t.ly_do === "loi_doc" ? "🛑" : t.ly_do === "it_chu" ? "📄"
                        : t.ly_do === "thieu_ngu_canh" ? "ℹ️" : "⚠️"}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="u-name tnum">Trang {t.so}</div>
                      <div className="u-mach">{LY_DO[t.ly_do] ?? t.ly_do}</div>
                    </div>
                    <button className="btn2 nho" type="button" disabled={busy !== ""}
                      onClick={() => {
                        setBusy("thu");
                        cmsDocThuSach(job.mon, job.khoi, job.tap, [t.so], true)
                          .then((r) => { setThu(r); setXemTrang(0); })
                          .catch((e) => loi(e, "Không đọc lại được"))
                          .finally(() => setBusy(""));
                      }}>Đọc lại</button>
                  </div>
                ))}
                {job.trang_soat.length > 30 && (
                  <div className="ns-ghi">…và {job.trang_soat.length - 30} trang nữa.</div>
                )}
              </div>
            </div>
          )}

          {jobs.length > 0 && (
            <div className="panel" style={{ marginTop: 14 }}>
              <div className="panel-h"><h3>Lần nạp gần đây</h3>
                <span className="vz-ghi">{jobs.length}</span></div>
              <div style={{ padding: "6px 14px 12px" }}>
                {jobs.map((j) => (
                  <button className="tep nut" key={j.id} type="button"
                    onClick={() => { setJob(j); cmsJobSach(j.id).then(setJob).catch(() => {}); }}>
                    <span className="tep-ic" aria-hidden>{j.mon === "toan" ? "📘" : "📗"}</span>
                    <div style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
                      <div className="u-name">{j.sach} · Tập {j.tap}</div>
                      <div className="u-mach tnum">{j.da_xong}/{j.tong} trang
                        {j.so_doan ? ` · ${j.so_doan} đoạn` : ""}</div>
                    </div>
                    <span className={"pill " + TT[j.trang_thai][0]}>{TT[j.trang_thai][1]}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
