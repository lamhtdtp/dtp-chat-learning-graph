import { useEffect, useState } from "react";
import { ApiError, cmsTongQuan } from "../api";
import type { CmsTongQuan } from "../types";

// Emoji theo mạch — mockup dùng emoji để nhận ra mạch từ xa. Mạch lạ -> 📘.
const EM: Record<string, string> = {
  "số tự nhiên": "🔢", "số nguyên": "➖", "phân số": "½", "số thập phân": "🔟",
  "các hình phẳng trong thực tiễn": "🔷", "tính đối xứng của hình phẳng": "🪞",
  "hình học trực quan": "📐", "thống kê": "📊", "xác suất": "🎲",
  "tỉ số và tỉ số phần trăm": "％", "dữ liệu và xác suất thực nghiệm": "📈",
};
const em = (m: string) => EM[m.trim().toLowerCase()] ?? "📘";

/** Trang Tổng quan của chuyên gia (REQ §2.1).
 *
 *  Ba khối trả lời ba câu khác nhau: quy mô (KPI) · mạch nào đang hụt (tiến độ)
 *  · phải làm gì tiếp (việc cần làm). Khối thứ ba là thứ khiến trang này khác
 *  một bảng số vô hồn — nó dẫn thẳng sang chỗ cần sửa.
 */
export function TongQuanView({ mon, khoi, onDi }: {
  mon: string; khoi: string; onDi: (v: "content" | "matrix") => void;
}) {
  const [d, setD] = useState<CmsTongQuan | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setD(null);
    cmsTongQuan(mon, khoi).then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được số liệu"));
  }, [mon, khoi]);

  if (err) return <div className="warn-box">⚠️ {err}</div>;
  if (!d) return null;
  const k = d.kpi;

  return (
    <>
      {/* Markup .kpi đúng hợp đồng §2.1: .ic → .v → .l, không đảo thứ tự */}
      <div className="kpis">
        <div className="kpi"><div className="ic ic-total">📚</div>
          <div className="v tnum">{k.tong_dv}</div><div className="l">Đơn vị kiến thức</div></div>
        <div className="kpi"><div className="ic ic-ok">✅</div>
          <div className="v tnum">{k.du_7_phan}</div><div className="l">Đã soạn đủ {k.tong_phan} phần</div></div>
        <div className="kpi"><div className="ic ic-ai">🎯</div>
          <div className="v tnum">{k.ycd}</div><div className="l">Yêu cầu cần đạt</div></div>
        <div className="kpi"><div className="ic ic-warn">✍️</div>
          <div className="v tnum">{k.dang_soan}</div><div className="l">Đang soạn dở</div></div>
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        <div className="panel">
          <div className="panel-h"><h3>Tiến độ theo mạch</h3>
            <span className="vz-ghi">phần đã soạn / (đơn vị × {k.tong_phan})</span></div>
          <div style={{ padding: "12px 16px 16px" }}>
            {d.theo_mach.length === 0
              ? <div className="viz-trong">Chưa có mạch nào trong danh mục.</div>
              : d.theo_mach.map((m) => (
                <button className="tqm" type="button" key={m.mach} onClick={() => onDi("content")}
                  title="Mở Chương trình & nội dung">
                  <span className="tqm-em">{em(m.mach)}</span>
                  <span className="tqm-ten">{m.mach}</span>
                  <span className="tqm-dv tnum">{m.so_dv} đơn vị</span>
                  <span className="tqm-track"><i style={{ width: `${m.phan_tram}%` }} /></span>
                  <b className="tqm-pct tnum">{m.phan_tram}%</b>
                </button>
              ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-h"><h3>Việc cần làm</h3></div>
          <div style={{ padding: "12px 16px 16px" }}>
            {d.viec_can_lam.length === 0
              ? <div className="viz-trong">Không còn việc nào đang dở. 🎉</div>
              : d.viec_can_lam.map((v) => (
                <div className="tqv" key={v.mo}>
                  <b className="tqv-so tnum">{v.so}</b>
                  <span className="tqv-mo">{v.mo}</span>
                  <button className="act txt" type="button"
                    onClick={() => onDi(v.di === "matrix" ? "matrix" : "content")}>Đi tới →</button>
                </div>
              ))}
          </div>
        </div>
      </div>
    </>
  );
}
