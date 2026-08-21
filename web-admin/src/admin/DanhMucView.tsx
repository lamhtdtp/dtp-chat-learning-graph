import { useEffect, useState } from "react";
import { ApiError, cmsDanhMuc } from "../api";
import type { DmHocKy } from "../types";

const EM: Record<string, string> = {
  "số tự nhiên": "🔢", "số nguyên": "➖", "phân số": "½", "số thập phân": "🔟",
  "các hình phẳng trong thực tiễn": "🔷", "tính đối xứng của hình phẳng": "🪞",
  "hình học trực quan": "📐", "thống kê": "📊", "xác suất": "🎲",
  "tỉ số và tỉ số phần trăm": "％", "dữ liệu và xác suất thực nghiệm": "📈",
};
const em = (m: string) => EM[m.trim().toLowerCase()] ?? "📘";
const PILL: Record<string, [string, string]> = {
  du: ["p-xong", "Đủ"], dang: ["p-duyet", "Đang soạn"], chua: ["p-nhap", "Chưa soạn"],
};

/** Cây danh mục: HỌC KỲ → mạch → đơn vị, kèm node ôn tập (REQ §2.3). */
export function DanhMucView({ mon, khoi, onSua }: {
  mon: string; khoi: string; onSua: (topicId: number) => void;
}) {
  const [ds, setDs] = useState<DmHocKy[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setDs(null);
    cmsDanhMuc(mon, khoi).then((r) => setDs(r.hoc_ky))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được danh mục"));
  }, [mon, khoi]);

  if (err) return <div className="warn-box">⚠️ {err}</div>;
  if (!ds) return null;
  if (!ds.length) return <div className="viz-trong">Chưa có đơn vị nào cho {mon} {khoi}.</div>;

  return (
    <>
      <div className="page-head">
        <div><h1>Quản lý danh mục</h1>
          <div className="ps">Học kỳ → mạch → đơn vị kiến thức. Node ôn tập là <b>view</b> gộp, không phải bài mới.</div></div>
      </div>
      {ds.map((hk) => (
        <div className="panel dmk" key={hk.hoc_ky}>
          <div className="panel-h"><h3>📚 HỌC KỲ {hk.hoc_ky === "hk1" ? 1 : 2}</h3>
            <span className="vz-ghi">{hk.mach.reduce((s, m) => s + m.so_dv, 0)} đơn vị</span></div>
          <div style={{ padding: "10px 14px 14px" }}>
            {hk.mach.map((m) => (
              <div className="dm-mach" key={m.mach}>
                <div className="dm-mh"><span className="dm-em">{em(m.mach)}</span>
                  <b>{m.mach}</b><span className="dm-n">{m.so_dv} đơn vị</span></div>
                {m.dv.map((d, i) => {
                  const [cls, nhan] = PILL[d.tinh_trang];
                  return (
                    <button className="dm-dv" type="button" key={d.topic_id}
                      onClick={() => onSua(d.topic_id)} title="Mở trình soạn">
                      <span className="dm-so tnum">{i + 1}</span>
                      <span className="dm-ten">{d.ten}</span>
                      <span className="dm-phan tnum">{d.da_soan}/{d.tong_phan} phần</span>
                      {d.ycd > 0 && <span className="dm-ycd tnum">🎯 {d.ycd}</span>}
                      <span className={"pill " + cls}>{nhan}</span>
                    </button>
                  );
                })}
                {/* Ôn tập chương: CUỐI mạch, thụt vào cùng cấp đơn vị */}
                <div className="dm-on">🔁 Ôn tập chương · {m.mach}
                  <span className="dm-oc">{m.on_tap.so_cau} câu</span></div>
              </div>
            ))}
            {/* Ôn tập cuối kỳ: cuối học kỳ, KHÔNG thụt */}
            <div className="dm-on ky">🏁 Ôn tập cuối học kỳ {hk.hoc_ky === "hk1" ? 1 : 2}
              <span className="dm-oc">{hk.on_tap_ky.so_cau} câu</span></div>
          </div>
        </div>
      ))}
    </>
  );
}
