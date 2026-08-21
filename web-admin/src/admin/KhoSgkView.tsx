import { useEffect, useState } from "react";
import { ApiError, cmsKhoSgk } from "../api";
import type { KhoSgk } from "../types";

// 4 bước khớp pipeline thật (app/ingestion). Chưa có job theo dõi tiến trình nên
// panel này hiện TRẠNG THÁI TĨNH của kho, không giả vờ đang chạy.
const BUOC = [
  ["Đọc trang & nhận dạng công thức", "OCR ảnh/PDF → văn bản"],
  ["Chia đoạn theo mục bài", "Theo chương · bài · trang"],
  ["Nhúng vào kho tri thức", "Vector hoá + ghi Qdrant"],
  ["Đối chiếu với danh mục chương trình", "Gắn môn · khối · sách"],
] as const;

/** Nạp sách bằng AI — số liệu kho + danh sách sách (REQ §2.4). */
export function KhoSgkView() {
  const [d, setD] = useState<KhoSgk | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    cmsKhoSgk().then(setD)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "Không tải được kho SGK"));
  }, []);

  if (err) return <div className="warn-box">⚠️ {err}</div>;
  if (!d) return null;

  return (
    <>
      <div className="page-head">
        <div><h1>Nạp sách bằng AI</h1>
          <div className="ps">Ảnh trang sách hoặc PDF → OCR → chia đoạn → kho tri thức</div></div>
        <div className="sp" />
        <span className="badge-ai">Nạp bằng CLI · UI upload chưa nối</span>
      </div>

      {/* Kho lỗi thì nói rõ số nào không đọc được, không hiện 0 như thể kho rỗng */}
      {d.kho_loi && (
        <div className="warn-box" style={{ marginBottom: 16 }}>
          ⚠️ Không đọc được kho tri thức (Qdrant). Số đoạn/trang đang hiện 0 vì
          <b> chưa đọc được</b>, không phải vì kho rỗng. Danh sách sách bên dưới vẫn đúng.
        </div>
      )}

      <div className="kpis">
        <div className="kpi"><div className="ic ic-total">📚</div>
          <div className="v tnum">{d.kpi.so_sach}</div><div className="l">Sách trong kho</div></div>
        <div className="kpi"><div className="ic ic-ai">📄</div>
          <div className="v tnum">{d.kpi.so_trang}</div><div className="l">Trang đã đọc</div></div>
        <div className="kpi"><div className="ic ic-ok">🧩</div>
          <div className="v tnum">{d.kpi.so_doan}</div><div className="l">Đoạn tri thức</div></div>
        <div className="kpi"><div className="ic ic-warn">🔖</div>
          <div className="v tnum">{d.kpi.pt_dan_nguon}%</div><div className="l">Có dẫn nguồn</div></div>
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        <div className="panel">
          <div className="panel-h"><h3>Sách trong kho</h3>
            <span className="vz-ghi">{d.sach.length} quyển</span></div>
          <div style={{ padding: "6px 14px 14px" }}>
            {d.sach.length === 0
              ? <div className="viz-trong">Chưa nạp quyển nào.
                  Dùng <code>python -m app.ingestion.cli</code>.</div>
              : d.sach.map((s) => (
                <div className="tep" key={s.id}>
                  <span className="tep-ic">📘</span>
                  <div style={{ minWidth: 0 }}>
                    <div className="u-name">{s.ten}</div>
                    <div className="u-mach">{s.mon} · {s.khoi}
                      {s.tap ? ` · Tập ${s.tap}` : ""} · {s.source_ref}</div>
                  </div>
                </div>
              ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-h"><h3>Các bước khi nạp một quyển</h3></div>
          <div style={{ padding: "12px 14px" }}>
            {BUOC.map(([ten, mo], i) => (
              <div className="nb cho" key={ten}>
                <span className="nb-ic">{i + 1}</span>
                <div><div className="nb-ten">{ten}</div><div className="nb-mo">{mo}</div></div>
              </div>
            ))}
            <div className="badge-man" style={{ marginTop: 10 }}>
              Hiện chạy bằng CLI trên server. Mockup UI upload:
              <code>mockup-nap-sach-ai.html</code>.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
