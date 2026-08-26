import { useEffect, useState } from "react";
import { ApiError, adminKetQua, tokenStore } from "../api";
import type { KetQuaHocSinh } from "../types";

/** Phút -> "3g 50p". "230p" bắt người đọc tự chia 60 trong đầu. */
function gio(phut: number): string {
  if (!phut) return "—";
  if (phut < 60) return `${phut} phút`;
  const g = Math.floor(phut / 60);
  const p = phut % 60;
  return p ? `${g}g ${p}p` : `${g} giờ`;
}

const TT_PILL: Record<string, [string, string]> = {
  dat: ["p-xong", "Đạt"], dang: ["p-duyet", "Đang học"], chua: ["p-nhap", "Chưa học"],
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return `${d.toLocaleDateString("vi-VN")} ${d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`;
};

/** Kết quả Kiểm tra nhanh của 1 học sinh — mở từ bảng Người dùng.
 *
 *  Hai lớp thông tin: gộp theo ĐƠN VỊ (thấy ngay chỗ nào đuối, làm đi làm lại
 *  mấy lần) và nhật ký TỪNG LẦN nộp (thấy tiến bộ theo thời gian). */
export function KetQuaDrawer({ userId, onClose }: { userId: number; onClose: () => void }) {
  const [d, setD] = useState<KetQuaHocSinh | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    adminKetQua(userId).then(setD).catch((e) => {
      if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); location.reload(); return; }
      setErr(e instanceof ApiError ? e.message : "Lỗi kết nối");
    });
  }, [userId]);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Kết quả học tập">
        <div className="dw-h">
          <div style={{ flex: 1 }}>
            <div className="eyebrow">Kết quả học tập</div>
            <h2>{d?.hoc_sinh.name ?? "Đang tải…"}</h2>
            {d && <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{d.hoc_sinh.email}</div>}
          </div>
          <button className="dw-close" type="button" onClick={onClose} aria-label="Đóng">✕</button>
        </div>

        <div className="dw-body">
          {err && <div className="warn-box">⚠️ {err}</div>}
          {!d && !err && <div style={{ color: "var(--ink-3)" }}>Đang tải…</div>}
          {d && d.theo_don_vi.length === 0 && (
            <div className="locked"><span className="lk">📭</span><div>
              <b>Chưa có lần làm bài nào.</b><br />
              <span style={{ fontSize: 12 }}>Kết quả chỉ được lưu từ khi tính năng này bật — các lượt làm trước đó không dựng lại được.</span>
            </div></div>
          )}
          {d && d.theo_don_vi.length > 0 && (
            <>
              {/* Hai ô đầu là con số HỌC SINH nhìn thấy trên vòng tiến độ. Trước
                  đây bảng này chỉ đếm lượt làm quiz, nên bài các em bấm "Đã hoàn
                  thành" không hiện ở đâu và giáo viên tưởng chưa học. */}
              <div className="kq-tong">
                <div className="kq-o"><b className="tnum">{d.so_dat}</b><span>đơn vị đạt</span></div>
                <div className="kq-o"><b className="tnum">{d.so_dang}</b><span>đang học</span></div>
                <div className="kq-o"><b className="tnum">{d.tong_lan}</b><span>lần kiểm tra</span></div>
                <div className="kq-o"><b className="tnum">{d.diem_tb}%</b><span>đúng trung bình</span></div>
                {/* Thời gian học: cùng service với /me/thoi-gian nên khớp đúng con
                    số học sinh thấy ở Hồ sơ học tập. */}
                <div className="kq-o"><b className="tnum">{gio(d.thoi_gian.tong_phut)}</b>
                  <span>tổng thời gian</span></div>
                <div className="kq-o"><b className="tnum">{gio(d.thoi_gian.bay_ngay_phut)}</b>
                  <span>7 ngày qua</span></div>
              </div>
              {/* Biểu đồ 14 ngày — thấy ngay em học đều hay học dồn. */}
              {d.thoi_gian.bieu_do.some((b) => b.phut > 0) && (
                <div className="kq-bd">
                  <div className="kq-bd-nhan">14 ngày gần đây
                    <span> · {d.thoi_gian.so_phien} phiên học
                      · mục tiêu {d.thoi_gian.muc_tieu_phut} phút/ngày</span></div>
                  <div className="kq-bd-khung">
                    {(() => {
                      const dinh = Math.max(Math.round(d.thoi_gian.muc_tieu_phut * 1.25),
                        ...d.thoi_gian.bieu_do.map((b) => b.phut), 1);
                      return d.thoi_gian.bieu_do.map((b) => (
                        <div className="kq-bd-cot" key={b.ngay}
                          title={`${b.ngay}: ${b.phut} phút`}>
                          <i className={(b.hom_nay ? "nay " : "") + (b.phut === 0 ? "khong" : "")}
                            style={{ height: b.phut === 0 ? 4 : `${Math.max(6, (b.phut / dinh) * 100)}%` }} />
                        </div>
                      ));
                    })()}
                  </div>
                </div>
              )}
              {d.tong_lan_on_tap > 0 && (
                <div className="kq-ghi">Ngoài ra có {d.tong_lan_on_tap} câu từ đề
                  {" "}<b>ôn tập cả mạch</b> — không tính vào điểm trung bình của từng bài.</div>
              )}

              <div className="esec">
                <div className="esec-h"><span className="n">📊</span> Theo đơn vị kiến thức</div>
                <table>
                  <thead><tr><th>Đơn vị</th><th>Trạng thái</th><th className="tnum">Thời gian</th><th className="tnum">Số lần</th><th className="tnum">Tốt nhất</th><th className="tnum">Gần nhất</th></tr></thead>
                  <tbody>
                    {d.theo_don_vi.map((g) => (
                      <tr key={g.topic_id}>
                        <td><div className="u-name">{g.ten}</div><div className="u-mach">{g.mach}</div></td>
                        <td><span className={"pill " + TT_PILL[g.trang_thai][0]}>
                          {TT_PILL[g.trang_thai][1]}</span></td>
                        <td className="tnum">{gio(g.phut)}
                          {g.so_phien > 0 && <span className="kq-mo"> · {g.so_phien} phiên</span>}</td>
                        <td className="tnum">{g.so_lan}
                          {g.so_lan_on_tap > 0 && <span className="kq-ot">+{g.so_lan_on_tap} ôn tập</span>}</td>
                        {/* Chưa làm bài kiểm tra của đơn vị -> "—", KHÔNG phải 0%:
                            0% đọc thành "làm và sai hết". */}
                        <td className="tnum">{g.tot_nhat === null ? "—" : `${g.tot_nhat}%`}</td>
                        <td>{g.gan_nhat === null ? <span className="kq-mo">—</span>
                          : <span className={"pill " + (g.gan_nhat >= 70 ? "p-xong" : "p-duyet")}>
                              {g.gan_nhat}%</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="esec">
                <div className="esec-h"><span className="n">🕒</span> Từng lần nộp
                  {d.tong_lan > d.lan.length && (
                    <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--ink-3)" }}>
                      hiện {d.lan.length} lần gần nhất
                    </span>
                  )}
                </div>
                {d.lan.map((x, i) => (
                  <div className="kq-lan" key={i}>
                    <span className={"pill " + (x.dat ? "p-xong" : "p-duyet")}>{x.diem}/{x.tong}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="u-name">{x.ten}
                        {x.nguon === "on_tap" && <span className="kq-ot">ôn tập</span>}</div>
                      <div className="u-mach">{fmt(x.luc)}</div>
                    </div>
                    <b className="tnum" style={{ fontSize: 13 }}>{x.phan_tram}%</b>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
