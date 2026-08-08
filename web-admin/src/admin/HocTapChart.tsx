import { useEffect, useState } from "react";
import { ApiError, adminOverview } from "../api";
import type { AdminOverview } from "../types";

const NGAY = 14;
const W = 720, H = 190, PAD_L = 34, PAD_R = 12, PAD_T = 12, PAD_B = 26;

const dm = (iso: string) => { const d = new Date(iso); return `${d.getDate()}/${d.getMonth() + 1}`; };

/** Đường: số lượt làm bài mỗi ngày. MỘT series nên không cần chú giải — tiêu đề
 *  đã nói nó là gì (quy tắc: 1 series thì bỏ legend). */
function DuongHoatDong({ data }: { data: AdminOverview["hoat_dong"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.so_lan));
  const x = (i: number) => PAD_L + (i * (W - PAD_L - PAD_R)) / Math.max(1, data.length - 1);
  const y = (v: number) => PAD_T + (1 - v / max) * (H - PAD_T - PAD_B);
  const d = data.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.so_lan).toFixed(1)}`).join(" ");
  // 3 mốc trục: 0 / giữa / max. Nhiều hơn là nhiễu cho biểu đồ cao 190px.
  const moc = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);

  return (
    <div className="viz" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Số lượt làm bài mỗi ngày">
        {moc.map((v) => (
          <g key={v}>
            <line className="viz-grid" x1={PAD_L} x2={W - PAD_R} y1={y(v)} y2={y(v)} />
            <text className="viz-tick" x={PAD_L - 7} y={y(v) + 3.5} textAnchor="end">{v}</text>
          </g>
        ))}
        {data.map((p, i) => (
          (i === 0 || i === data.length - 1 || i === Math.floor(data.length / 2)) &&
          <text className="viz-tick" key={p.ngay} x={x(i)} y={H - 8} textAnchor="middle">{dm(p.ngay)}</text>
        ))}
        <path className="viz-line" d={d} />
        {hover != null && <line className="viz-cross" x1={x(hover)} x2={x(hover)} y1={PAD_T} y2={H - PAD_B} />}
        {data.map((p, i) => (
          <circle key={p.ngay} className={"viz-dot" + (hover === i ? " on" : "")}
            cx={x(i)} cy={y(p.so_lan)} r={hover === i ? 5 : 3} />
        ))}
        {/* Vùng bắt chuột rộng hơn chấm — chấm 3px thì gần như không trỏ trúng */}
        {data.map((p, i) => (
          <rect key={"h" + p.ngay} x={x(i) - 12} y={0} width={24} height={H}
            fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {hover != null && (
        <div className="viz-tip" style={{ left: `${(x(hover) / W) * 100}%` }}>
          <b>{data[hover].so_lan}</b> lượt · {dm(data[hover].ngay)}
        </div>
      )}
    </div>
  );
}

/** Cột ngang: đơn vị học sinh trượt nhiều nhất. Nhãn nằm ngoài cột nên đọc được
 *  cả khi cột ngắn; màu chỉ nhấn mạnh, con số mới là thứ mang thông tin. */
function CotKhoNhat({ data, toiThieu }: { data: AdminOverview["kho_nhat"]; toiThieu: number }) {
  if (!data.length) {
    return <div className="viz-trong">Chưa đủ dữ liệu — cần ít nhất {toiThieu} lượt làm trên một đơn vị.</div>;
  }
  return (
    <div className="viz-bars">
      {data.map((u) => (
        <div className="viz-bar" key={u.topic_id}>
          <div className="vb-ten" title={u.ten}>{u.ten}</div>
          <div className="vb-track"><i style={{ width: `${u.ty_le_truot}%` }} /></div>
          <b className="vb-so tnum">{u.ty_le_truot}%</b>
          <span className="vb-n tnum">{u.so_lan} lượt</span>
        </div>
      ))}
    </div>
  );
}

/** Khối thống kê học tập cho trang Tổng quan. Ẩn hẳn khi chưa có lượt làm nào —
 *  biểu đồ rỗng chỉ làm người xem tưởng hệ thống hỏng. */
export function HocTapChart() {
  const [d, setD] = useState<AdminOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    adminOverview(NGAY).then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được số liệu"));
  }, []);

  if (err) return <div className="warn-box" style={{ marginBottom: 22 }}>⚠️ {err}</div>;
  if (!d) return null;

  return (
    <div className="viz-root">
      {/* 3 tile nên ép 3 cột: .kpis mặc định 4 cột sẽ chừa một ô trống lệch hẳn */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)", marginBottom: 14 }}>
        <div className="kpi"><div className="v tnum">{d.tong.hoc_sinh}</div><div className="l">Học sinh đã làm bài</div></div>
        <div className="kpi"><div className="v tnum">{d.tong.luot_lam}</div><div className="l">Lượt kiểm tra nhanh</div></div>
        <div className="kpi"><div className="v tnum">{d.tong.ty_le_dat}%</div><div className="l">Tỉ lệ đạt</div></div>
      </div>

      <div className="grid2" style={{ marginBottom: 22 }}>
        <div className="panel">
          <div className="panel-h"><h3>Lượt làm bài {NGAY} ngày qua</h3></div>
          <div style={{ padding: "10px 14px 4px" }}>
            {d.tong.luot_lam === 0
              ? <div className="viz-trong">Chưa có lượt làm bài nào.</div>
              : <DuongHoatDong data={d.hoat_dong} />}
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><h3>Đơn vị học sinh trượt nhiều nhất</h3></div>
          <div style={{ padding: "12px 14px" }}>
            <CotKhoNhat data={d.kho_nhat} toiThieu={d.toi_thieu_luot} />
          </div>
        </div>
      </div>
    </div>
  );
}
