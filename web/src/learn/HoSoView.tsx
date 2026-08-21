import { useEffect, useState } from "react";
import { ApiError, getThoiGian, getYcd, tokenStore } from "../api";
import type { ThoiGianHoc, YcdMach } from "../types";

const MD: Record<string, string> = {
  nhan_biet: "Nhận biết", thong_hieu: "Thông hiểu", van_dung: "Vận dụng",
  van_dung_cao: "Vận dụng cao", de: "Dễ", trung_binh: "TB", kho: "Khó",
};
const dm = (iso: string) => {
  const d = new Date(iso);
  return `${d.getDate()}/${d.getMonth() + 1} ${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** Hồ sơ học tập của học sinh — 4 khối theo REQ §3.6. */
export function HoSoView({ onMoBai }: { onMoBai?: (topicId: number, phan?: string) => void }) {
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

  return (
    <article className="lesson">
      <span className="eyebrow">📈 Hồ sơ học tập</span>
      <h1>Em học tới đâu rồi</h1>

      {/* ── Khối 1: 4 ô thời gian ── */}
      <h3><span className="hi">⏱</span> Thời gian học</h3>
      <div className="hs4">
        <div className="hs4-o"><b className="num">{tg.hom_nay_phut}′</b><span>Hôm nay</span>
          {tg.dat_muc_tieu && <i className="hs4-dat">✓ đạt mục tiêu</i>}</div>
        <div className="hs4-o"><b className="num">{tg.bay_ngay_phut}′</b><span>7 ngày qua</span></div>
        <div className="hs4-o"><b className="num">{tg.tong_phut}′</b><span>Từ đầu năm</span></div>
        <div className="hs4-o"><b className="num">{tg.so_phien}</b><span>Số phiên học</span></div>
      </div>

      {/* ── Khối 2: biểu đồ 14 ngày ── */}
      <h3><span className="hi">📊</span> 14 ngày gần đây</h3>
      <div className="hsbd">
        {/* Đường mục tiêu nét đứt — có nó thì cột cao/thấp mới có nghĩa */}
        {/* Đường mục tiêu phải tính TRONG vùng vẽ: khung có padding-bottom 22px
            cho nhãn ngày và 10px trên, nên trừ ra rồi mới nhân tỉ lệ. */}
        <div className="hsbd-mt" style={{ bottom: `calc(22px + (100% - 32px) * ${tyLeMt})` }}>
          <span>{tg.muc_tieu_phut}′ mục tiêu</span>
        </div>
        {tg.bieu_do.map((b) => (
          <div className="hsbd-c" key={b.ngay} title={`${b.ngay}: ${b.phut} phút`}>
            {/* Ngày không học: vạch xám 5px — để 0 thì đọc thành "không có dữ liệu" */}
            <i className={(b.hom_nay ? "nay " : "") + (b.phut === 0 ? "khong" : "")}
              style={{ height: b.phut === 0 ? 5 : `${Math.max(6, (b.phut / maxPhut) * 100)}%` }} />
            <span>{new Date(b.ngay).getDate()}</span>
          </div>
        ))}
      </div>

      {/* ── Khối 3: lịch sử phiên ── */}
      <h3><span className="hi">🕒</span> Lịch sử học tập</h3>
      {tg.lich_su.length === 0
        ? <p className="lead">Chưa có phiên học nào được ghi.</p>
        : tg.lich_su.map((p, i) => (
          <div className="hsls" key={i}>
            <span className="hsls-luc num">{dm(p.luc)}</span>
            <button className="hsls-ten" type="button" onClick={() => onMoBai?.(p.topic_id)}>{p.ten}</button>
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
        ))}

      {/* ── Khối 4: đạt tới đâu theo yêu cầu cần đạt ── */}
      <h3><span className="hi">🎯</span> Đạt tới đâu theo yêu cầu cần đạt</h3>
      {!ycd?.length
        ? <p className="lead">Chưa có ma trận đặc tả cho lớp này.</p>
        : ycd.map((m) => (
          <div className="pmach" key={m.mach}>
            <div className="pmach-h">{m.mach}</div>
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
