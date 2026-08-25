import { useEffect, useState } from "react";
import { ApiError, getThoiGian, getYcd, tokenStore } from "../api";
import type { ThoiGianHoc, YcdMach } from "../types";

const MD: Record<string, string> = {
  nhan_biet: "Nhận biết", thong_hieu: "Thông hiểu", van_dung: "Vận dụng",
  van_dung_cao: "Vận dụng cao", de: "Dễ", trung_binh: "TB", kho: "Khó",
};
const THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

/** Phút -> chuỗi người đọc được. "230′" bắt học sinh tự chia 60 trong đầu;
 *  mockup ghi "3g 50p". Dưới một giờ vẫn để "N phút" cho gọn. */
function gio(phut: number): string {
  if (phut < 60) return `${phut} phút`;
  const g = Math.floor(phut / 60);
  const p = phut % 60;
  return p ? `${g}g ${p}p` : `${g} giờ`;
}

/** Ngày của phiên: hai ngày gần nhất gọi bằng tên, xa hơn thì d/m. Học sinh nhớ
 *  "hôm qua" chứ không nhớ "23/8". */
function ngayPhien(iso: string): [string, string] {
  const d = new Date(iso);
  const gio_ = `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
  const hnay = new Date();
  const chenh = Math.round(
    (new Date(hnay.getFullYear(), hnay.getMonth(), hnay.getDate()).getTime()
      - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86_400_000);
  if (chenh === 0) return ["Hôm nay", gio_];
  if (chenh === 1) return ["Hôm qua", gio_];
  return [`${d.getDate()}/${d.getMonth() + 1}`, gio_];
}

/** Hồ sơ học tập của học sinh — 4 khối theo REQ §3.6. */
export function HoSoView({ onMoBai, ten }: {
  onMoBai?: (topicId: number, phan?: string) => void;
  /** Tên học sinh — mockup đặt tiêu đề là "An · Toán lớp 6". */
  ten?: string;
}) {
  const [tg, setTg] = useState<ThoiGianHoc | null>(null);
  const [ycd, setYcd] = useState<YcdMach[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const loi = (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); location.reload(); return; }
      setErr(e instanceof ApiError ? e.message : "Không tải được hồ sơ");
    };
    getThoiGian(14).then(setTg).catch(loi);
    getYcd().then((r) => setYcd(r.mach)).catch(loi);
  }, []);

  if (err) return <article className="lesson"><div className="lesson-empty">⚠️ {err}</div></article>;
  if (!tg) return <article className="lesson"><div className="lesson-empty">Đang tải hồ sơ…</div></article>;

  // Trần biểu đồ = 1.25× mục tiêu (hoặc cao hơn nếu có ngày vượt). Lấy đúng bằng
  // mục tiêu thì hôm nào chưa ai học, đường mục tiêu nằm ở 100% -> tràn ra ngoài
  // khung, cắt ngang tiêu đề (đã gặp thật).
  const maxPhut = Math.max(Math.round(tg.muc_tieu_phut * 1.25),
                           ...tg.bieu_do.map((b) => b.phut), 1);
  const tyLeMt = Math.min(1, tg.muc_tieu_phut / maxPhut);
  // Trung bình tính trên NGÀY CÓ HỌC, không chia đều 14 ngày: nghỉ cuối tuần
  // kéo trung bình xuống rồi báo "12 phút/ngày" trong khi hôm nào học cũng 25.
  const ngayCoHoc = tg.bieu_do.filter((b) => b.phut > 0);
  const tbNgay = ngayCoHoc.length
    ? Math.round(ngayCoHoc.reduce((t, b) => t + b.phut, 0) / ngayCoHoc.length) : 0;

  return (
    <article className="lesson">
      <span className="eyebrow">📈 Hồ sơ học tập</span>
      <h1>{ten ? `${ten} · Toán lớp 6` : "Em học tới đâu rồi"}</h1>
      {ngayCoHoc.length > 0 && (
        <p className="lead">Học {ngayCoHoc.length}/{tg.bieu_do.length} ngày gần đây,
          {" "}trung bình {tbNgay} phút mỗi ngày có học.</p>
      )}

      {/* ── Khối 1: 4 ô thời gian ── */}
      <h3><span className="hi">⏱</span> Thời gian học</h3>
      <div className="hs4">
        <div className={"hs4-o" + (tg.dat_muc_tieu ? " dat" : "")}>
          <b className="num">{gio(tg.hom_nay_phut)}</b><span>Hôm nay</span>
          {tg.dat_muc_tieu && <i className="hs4-dat">✓ đạt mục tiêu</i>}</div>
        <div className="hs4-o"><b className="num">{gio(tg.bay_ngay_phut)}</b><span>7 ngày qua</span></div>
        <div className="hs4-o"><b className="num">{gio(tg.tong_phut)}</b><span>Từ đầu năm</span></div>
        <div className="hs4-o"><b className="num">{tg.so_phien}</b><span>Phiên học</span></div>
      </div>

      {/* ── Khối 2: biểu đồ 14 ngày ── */}
      <h3><span className="hi">📊</span> 14 ngày gần đây</h3>
      {/* Chú thích mục tiêu nằm ở ĐẦU khung, không đè lên đường: nhãn cũ đặt
          sát mép phải nên bị cắt mất chữ trên màn hẹp. */}
      {/* Chỉ CHÚ THÍCH, không lặp lại tiêu đề đã có ở <h3> ngay trên. */}
      <div className="hsbd-dau">
        <span className="hsbd-cg">— — mục tiêu {tg.muc_tieu_phut} phút/ngày</span>
      </div>
      <div className="hsbd">
        {/* Đường mục tiêu phải tính TRONG vùng vẽ: khung có padding-bottom 22px
            cho nhãn ngày và 10px trên, nên trừ ra rồi mới nhân tỉ lệ. */}
        <div className="hsbd-mt" style={{ bottom: `calc(22px + (100% - 32px) * ${tyLeMt})` }} />
        {tg.bieu_do.map((b) => (
          <div className="hsbd-c" key={b.ngay} title={`${b.ngay}: ${b.phut} phút`}>
            {/* Ngày không học: vạch xám 5px — để 0 thì đọc thành "không có dữ liệu" */}
            <i className={(b.hom_nay ? "nay " : "") + (b.phut === 0 ? "khong" : "")}
              style={{ height: b.phut === 0 ? 5 : `${Math.max(6, (b.phut / maxPhut) * 100)}%` }} />
            {/* Nhãn THỨ, không phải số ngày: học sinh nhận ra "cuối tuần mình
                nghỉ" ngay, còn "12, 13, 14" thì phải tự nhẩm. */}
            <span className={b.hom_nay ? "nay" : undefined}>
              {THU[new Date(b.ngay).getDay()]}</span>
          </div>
        ))}
      </div>

      {/* ── Khối 3: lịch sử phiên ── */}
      <h3><span className="hi">🕒</span> Lịch sử học tập</h3>
      {tg.lich_su.length === 0
        ? <p className="lead">Chưa có phiên học nào được ghi.</p>
        : tg.lich_su.map((p, i) => {
          const [ng, gi] = ngayPhien(p.luc);
          return (
          <div className={"hsls" + (p.dang_hoc ? " dang" : "")} key={i}>
            <span className="hsls-luc"><b>{ng}</b><i className="num">{gi}</i></span>
            <div className="hsls-than">
            <button className="hsls-ten" type="button" onClick={() => onMoBai?.(p.topic_id)}>{p.ten}</button>
            <div className="hsls-tags">
            <span className="hsls-nh">⏱ {p.phut} phút</span>
            {p.quiz && (
              <span className={"hsls-nh " + (p.quiz.dat ? "ok" : "no")}>
                {p.quiz.dat ? "✅" : "△"} Kiểm tra {p.quiz.diem}/{p.quiz.tong}
              </span>
            )}
            {/* Mẫu số là số phần ĐANG HIỆN của bài đó, không phải 7 cố định */}
            {p.doc_y > 0 && <span className="hsls-nh">Đọc {p.doc_x}/{p.doc_y} phần</span>}
            {p.so_hoi > 0 && <span className="hsls-nh">💬 Hỏi trợ lý {p.so_hoi} câu</span>}
            {p.dang_hoc && <span className="hsls-nh dang">● đang học</span>}
            </div>
            </div>
          </div>
          );
        })}

      {/* ── Khối 4: đạt tới đâu theo yêu cầu cần đạt ── */}
      <h3><span className="hi">🎯</span> Đạt tới đâu theo yêu cầu cần đạt</h3>
      {!ycd?.length
        ? <p className="lead">Chưa có ma trận đặc tả cho lớp này.</p>
        : ycd.map((m) => (
          <div className="pmach" key={m.mach}>
            {(() => {
              const dat = m.ycd.filter((y) => y.trang_thai === "dat").length;
              const pt = m.ycd.length ? Math.round((dat / m.ycd.length) * 100) : 0;
              return (
                <div className="pmach-h">
                  <span className="tt">{m.mach}</span>
                  <div className="bar-track"><div className="bar-fill" style={{ width: `${pt}%` }} /></div>
                  <b className="num">{pt}%</b>
                </div>
              );
            })()}
            {m.ycd.map((y, i) => (
              <div className="ycd-row" key={i}>
                <span className={"badge " + (y.trang_thai === "dat" ? "b-dat"
                  : y.trang_thai === "dang" ? "b-dang" : "b-chua")}>
                  {y.trang_thai === "dat" ? "Đạt" : y.trang_thai === "dang" ? "Đang học" : "Chưa học"}
                </span>
                <span className="ycd-tx">{y.ycd}</span>
                <span className="ycd-md">{MD[y.muc_do] ?? y.muc_do}</span>
                {/* "Học lại" chỉ hiện khi sai ≥ 2: sai một lần là chuyện bình
                    thường, gắn nhãn ngay sẽ thành lời phê. */}
                {y.sai >= 2 && (
                  <>
                    <span className="ycd-sai">sai {y.sai} lần</span>
                    <button className="ycd-hl" type="button"
                      onClick={() => onMoBai?.(y.topic_id, "kien_thuc")}>Học lại ↗</button>
                  </>
                )}
              </div>
            ))}
          </div>
        ))}
    </article>
  );
}
