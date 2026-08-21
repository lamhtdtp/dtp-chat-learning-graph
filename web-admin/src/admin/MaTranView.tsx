import { useEffect, useState } from "react";
import { ApiError, cmsMaTran } from "../api";
import type { MaTran } from "../types";

// Ma trận thật dùng 3 mức (matrix_parser.MucDo = de|trung_binh|kho), KHÔNG phải
// 4 mức nhận biết/thông hiểu/vận dụng như REQ §2.5 mô tả. Giữ cả hai bộ nhãn để
// hiện đúng dù nạp từ nguồn nào.
const MD: Record<string, string> = {
  de: "Dễ", trung_binh: "Trung bình", kho: "Khó",
  nhan_biet: "Nhận biết", thong_hieu: "Thông hiểu",
  van_dung: "Vận dụng", van_dung_cao: "Vận dụng cao",
};

/** Đối chiếu ma trận đặc tả với danh mục (REQ §2.5). Chỉ đọc — không gán, không
 *  tạo đơn vị mới. */
export function MaTranView({ mon, khoi, onSua }: {
  mon: string; khoi: string; onSua?: (topicId: number) => void;
}) {
  const [d, setD] = useState<MaTran | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setD(null);
    cmsMaTran(mon, khoi).then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được ma trận"));
  }, [mon, khoi]);

  if (err) return <div className="warn-box">⚠️ {err}</div>;
  if (!d) return null;
  const tongTl = Object.values(d.ti_le).reduce((a, b) => a + b, 0);

  return (
    <>
      <div className="page-head">
        <div><h1>Ma trận đặc tả</h1>
          <div className="ps">{d.so_dong} dòng yêu cầu cần đạt · {mon} {khoi}</div></div>
      </div>

      {/* Nạp .docx VẪN tự tạo đơn vị chưa có trong danh mục (quyết định (b)) —
          nhưng không để nó xảy ra âm thầm: tên lấy thô từ Word nên hay trùng lặp
          hoặc sai chính tả so với đơn vị đã có. */}
      {d.tu_ma_tran.length > 0 && (
        <div className="warn-box mt-canh">
          <b>⚠️ {d.tu_ma_tran.length} đơn vị kiến thức do lần nạp ma trận tự tạo.</b>
          <div style={{ marginTop: 4 }}>
            Tên lấy nguyên từ tệp .docx nên có thể trùng lặp hoặc lệch chính tả với
            đơn vị đã có trong danh mục. Rà lại rồi gộp/đổi tên nếu cần.
          </div>
          <div className="mt-dsm">
            {d.tu_ma_tran.slice(0, 12).map((t) => (
              <button className="act txt" type="button" key={t.topic_id}
                onClick={() => onSua?.(t.topic_id)} title={`${t.mach} / ${t.ten}`}>
                {t.ten}
              </button>
            ))}
            {d.tu_ma_tran.length > 12 && (
              <span className="badge-man">… và {d.tu_ma_tran.length - 12} đơn vị nữa</span>
            )}
          </div>
        </div>
      )}

      {d.so_dong === 0
        ? <div className="viz-trong">Chưa nạp ma trận cho {mon} {khoi}.
            Nạp bằng <code>python -m app.exam.load_matrix_cli</code>.</div>
        : (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
            <div className="kpi"><div className="ic ic-ok">✅</div>
              <div className="v tnum">{d.tong.khop}</div><div className="l">Khớp chắc chắn (≥80%)</div></div>
            <div className="kpi"><div className="ic ic-warn">⚠️</div>
              <div className="v tnum">{d.tong.xem_lai}</div><div className="l">Cần xem lại (50–80%)</div></div>
            <div className="kpi"><div className="ic ic-total">✋</div>
              <div className="v tnum">{d.tong.chua_gan}</div><div className="l">Chưa gán (&lt;50%)</div></div>
            <div className="kpi"><div className="ic ic-ai">—</div>
              <div className="v tnum">{d.tong.chua_do}</div><div className="l">Chưa có dữ liệu đối chiếu</div></div>
          </div>

          <div className="grid2" style={{ alignItems: "start" }}>
            <div className="panel">
              <div className="panel-h"><h3>Tỉ lệ theo mức độ</h3>
                {/* Tổng phải ~100%: lệch nhiều là dấu hiệu ô gộp bị cộng sai */}
                <span className={"vz-ghi" + (Math.abs(tongTl - 100) > 1 ? " canh" : "")}>
                  tổng {tongTl.toFixed(0)}%</span></div>
              <div style={{ padding: "12px 16px 16px" }}>
                {Object.entries(d.ti_le).length === 0
                  ? <div className="viz-trong">Không có dữ liệu tỉ lệ.</div>
                  : Object.entries(d.ti_le).map(([md, tl]) => (
                    <div className="mt-bar" key={md}>
                      <span className="mt-bt">{MD[md] ?? md}</span>
                      <span className="mt-tr"><i style={{ width: `${tl}%` }} /></span>
                      <b className="mt-bs tnum">{tl.toFixed(0)}%</b>
                    </div>
                  ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-h"><h3>Ánh xạ vào danh mục</h3>
                <span className="vz-ghi">hiện {d.anh_xa.length}/{d.so_dong} dòng</span></div>
              <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
                <table>
                  <thead><tr><th>Mức độ</th><th>Yêu cầu cần đạt</th><th>Đơn vị kiến thức</th><th>Khớp</th></tr></thead>
                  <tbody>
                    {d.anh_xa.map((r, i) => (
                      <tr key={i}>
                        <td><span className="md-nh">{MD[r.muc_do] ?? r.muc_do}</span></td>
                        <td className="mt-ycd">{r.ycd}</td>
                        <td>
                          <div className="u-name">{r.don_vi}</div>
                          {/* Tên trong .docx khác tên danh mục -> nói ra, đó là lý
                              do điểm thấp; không nói thì người duyệt phải tự đoán */}
                          {r.lech_ten && <div className="u-mach">.docx: “{r.ten_nguon}”</div>}
                        </td>
                        <td>{r.diem === null
                          ? <span className="dk chua">—</span>
                          : <span className={"dk " + r.loai}>{r.diem}%</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
