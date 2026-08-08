import { useEffect, useState } from "react";
import { ApiError, adminKetQua, tokenStore } from "../api";
import type { KetQuaHocSinh } from "../types";

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
            <div className="eyebrow">Kết quả kiểm tra nhanh</div>
            <h2>{d?.hoc_sinh.name ?? "Đang tải…"}</h2>
            {d && <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{d.hoc_sinh.email}</div>}
          </div>
          <button className="dw-close" type="button" onClick={onClose} aria-label="Đóng">✕</button>
        </div>

        <div className="dw-body">
          {err && <div className="warn-box">⚠️ {err}</div>}
          {!d && !err && <div style={{ color: "var(--ink-3)" }}>Đang tải…</div>}
          {d && d.tong_lan === 0 && (
            <div className="locked"><span className="lk">📭</span><div>
              <b>Chưa có lần làm bài nào.</b><br />
              <span style={{ fontSize: 12 }}>Kết quả chỉ được lưu từ khi tính năng này bật — các lượt làm trước đó không dựng lại được.</span>
            </div></div>
          )}
          {d && d.tong_lan > 0 && (
            <>
              <div className="kq-tong">
                <div className="kq-o"><b className="tnum">{d.tong_lan}</b><span>lần làm</span></div>
                <div className="kq-o"><b className="tnum">{d.so_lan_dat}</b><span>lần đạt</span></div>
                <div className="kq-o"><b className="tnum">{d.diem_tb}%</b><span>đúng trung bình</span></div>
              </div>

              <div className="esec">
                <div className="esec-h"><span className="n">📊</span> Theo đơn vị kiến thức</div>
                <table>
                  <thead><tr><th>Đơn vị</th><th className="tnum">Số lần</th><th className="tnum">Tốt nhất</th><th className="tnum">Gần nhất</th></tr></thead>
                  <tbody>
                    {d.theo_don_vi.map((g) => (
                      <tr key={g.topic_id}>
                        <td><div className="u-name">{g.ten}</div><div className="u-mach">{g.mach}</div></td>
                        <td className="tnum">{g.so_lan}</td>
                        <td className="tnum">{g.tot_nhat}%</td>
                        <td><span className={"pill " + (g.dat ? "p-xong" : "p-duyet")}>{g.gan_nhat}%</span></td>
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
                      <div className="u-name">{x.ten}</div>
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
