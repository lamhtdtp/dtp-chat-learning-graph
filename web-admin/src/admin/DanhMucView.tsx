import { useEffect, useState } from "react";
import { ApiError, cmsDanhMuc, cmsOnTap } from "../api";
import type { DmHocKy, OnTap } from "../types";
import { GopTrung } from "./GopTrung";

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
export function DanhMucView({ mon, khoi, onSua, toast }: {
  mon: string; khoi: string; onSua: (topicId: number) => void;
  toast: (m: string) => void;
}) {
  const [ds, setDs] = useState<DmHocKy[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Node ôn tập đang mở + nội dung của nó. Không phải bài học nên không có trình
  // soạn — bấm vào phải XEM ĐƯỢC nó gộp những bài nào, nếu không thì node chỉ là
  // một dòng chữ vô dụng.
  const [mo, setMo] = useState<string | null>(null);
  const [ot, setOt] = useState<Record<string, OnTap | "dang" | { loi: string }>>({});

  const xemOnTap = async (pham_vi: string, gia_tri: string) => {
    const k = `${pham_vi}:${gia_tri}`;
    // Không gọi với giá trị rỗng: server sẽ 400, mà lỗi thật là dữ liệu danh mục
    // thiếu tên mạch/học kỳ — nói đúng chỗ đó.
    if (!gia_tri.trim()) {
      setMo(k);
      setOt((o) => ({ ...o, [k]: { loi: "Mạch/học kỳ này chưa có tên trong danh mục." } }));
      return;
    }
    setMo(mo === k ? null : k);
    if (ot[k] || mo === k) return;
    setOt((o) => ({ ...o, [k]: "dang" }));
    try {
      const d = await cmsOnTap(pham_vi, gia_tri, mon, khoi);
      setOt((o) => ({ ...o, [k]: d }));
    } catch (e) {
      // Nói ĐÚNG lý do: `catch {}` trơn từng làm mất một lỗi thiếu proxy, chỉ
      // thấy "không tải được" mà không lần ra được vì sao.
      setOt((o) => ({ ...o, [k]: { loi: e instanceof ApiError ? e.message : "Không gọi được máy chủ" } }));
    }
  };

  const KhoiOnTap = ({ pham_vi, gia_tri, so_cau, ky }: {
    pham_vi: string; gia_tri: string; so_cau: number; ky?: boolean;
  }) => {
    const k = `${pham_vi}:${gia_tri}`;
    const d = ot[k];
    const dangMo = mo === k;
    return (
      <>
        <button className={"dm-on" + (ky ? " ky" : "")} type="button"
          aria-expanded={dangMo} onClick={() => xemOnTap(pham_vi, gia_tri)}>
          {ky ? `🏁 Ôn tập cuối học kỳ ${gia_tri === "hk1" ? 1 : 2}` : `🔁 Ôn tập chương · ${gia_tri}`}
          <span className="dm-oc">{so_cau} câu · {dangMo ? "thu lại ▴" : "xem ▾"}</span>
        </button>
        {dangMo && (
          <div className={"dm-otb" + (ky ? " ky" : "")}>
            {d === "dang" ? <span className="badge-man">Đang tải…</span>
              : !d || "loi" in d ? <span className="badge-man">⚠️ {(d as { loi: string })?.loi ?? "Không tải được phạm vi ôn tập."}</span>
              : (
                <>
                  <div className="dm-otm">
                    Gộp <b>{d.so_bai}</b> bài · <b>{d.ycd}</b> yêu cầu cần đạt · đề <b>{d.so_cau_de}</b> câu
                    {d.chua_xong > 0 && <> · <span className="dm-otc">{d.chua_xong} bài chưa học xong</span></>}
                  </div>
                  <div className="dm-otl">
                    {d.bai.map((x) => (
                      <span className={"dm-otp" + (x.co_noi_dung ? "" : " trong")} key={x.topic_id}
                        title={x.co_noi_dung ? x.ten : `${x.ten} — chưa có nội dung`}>
                        {x.co_noi_dung ? "" : "⚠️ "}{x.ten}
                      </span>
                    ))}
                  </div>
                  {d.can_nho.length > 0 && (
                    <div className="dm-otn">💡 {d.can_nho.length} ý “cần nhớ” lấy từ các bài trên</div>
                  )}
                </>
              )}
          </div>
        )}
      </>
    );
  };

  const [lan, setLan] = useState(0);        // gộp xong -> tải lại cây
  useEffect(() => {
    setDs(null);
    cmsDanhMuc(mon, khoi).then((r) => setDs(r.hoc_ky))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được danh mục"));
  }, [mon, khoi, lan]);

  if (err) return <div className="warn-box">⚠️ {err}</div>;
  if (!ds) return null;
  if (!ds.length) return <div className="viz-trong">Chưa có đơn vị nào cho {mon} {khoi}.</div>;

  return (
    <>
      <div className="page-head">
        <div><h1>Quản lý danh mục</h1>
          <div className="ps">{mon} · {khoi} — Học kỳ → mạch → đơn vị. Node ôn tập là <b>view</b> gộp, không phải bài mới.</div></div>
      </div>
      <GopTrung mon={mon} khoi={khoi} toast={toast} onXong={() => setLan((n) => n + 1)} />
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
                <KhoiOnTap pham_vi="mach" gia_tri={m.mach} so_cau={m.on_tap.so_cau} />
              </div>
            ))}
            {/* Ôn tập cuối kỳ: cuối học kỳ, KHÔNG thụt */}
            <KhoiOnTap pham_vi="hoc_ky" gia_tri={hk.hoc_ky} so_cau={hk.on_tap_ky.so_cau} ky />
          </div>
        </div>
      ))}
    </>
  );
}
