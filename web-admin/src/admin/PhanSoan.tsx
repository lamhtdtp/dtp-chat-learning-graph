import { useState } from "react";
import { ApiError, cmsAiPhan, cmsLuuBoCuc } from "../api";
import { SoanHtml } from "../components/SoanHtml";
import type { CmsPhan } from "../types";

const MO: Record<string, string> = {
  khoi_dong: "Dẫn vào bài, gợi tò mò — không dạy kiến thức mới",
  hoat_dong: "Học sinh tự làm để tự phát hiện ra kiến thức",
  kien_thuc: "Định nghĩa, tính chất cốt lõi — phần bắt buộc",
  minh_hoa: "Ảnh và video minh hoạ",
  vi_du: "Ví dụ có lời giải từng bước",
  luyen_tap: "Bài từ nhận biết đến vận dụng, có đáp số",
  bai_tap: "Bài về nhà, không kèm lời giải",
};
// Hai phần này không phải HTML tự do -> nội dung do khối riêng bên dưới lo.
const KHONG_HTML = new Set(["minh_hoa", "vi_du"]);
// id phần -> khoá trong Draft (kien_thuc lưu ở cột `khai_niem`).
const COT: Record<string, string> = {
  khoi_dong: "khoi_dong", hoat_dong: "hoat_dong", kien_thuc: "khai_niem",
  luyen_tap: "luyen_tap", bai_tap: "bai_tap",
};

/** Bố cục 7 phần GỘP LUÔN nội dung: mỗi hàng vừa là chỗ đổi thứ tự/ẩn/hiện, vừa
 *  là chỗ soạn phần đó (REQ §2.2 + yêu cầu gộp).
 *
 *  Trước đây danh sách bố cục ở trên, các ô soạn ở dưới — chuyên gia phải nhớ hàng
 *  thứ mấy ứng với ô nào, và số thứ tự ở hai chỗ không nằm cạnh nhau để đối chiếu.
 */
export function PhanSoan({ topicId, banDau, giaTri, onDoi, toast, mediaSlot, viDuSlot }: {
  topicId: number;
  banDau: CmsPhan[];
  /** Nội dung hiện tại theo khoá cột trong Draft. */
  giaTri: Record<string, string>;
  onDoi: (cot: string, html: string) => void;
  toast: (m: string) => void;
  /** Khối Minh hoạ (ảnh/video) — render vào đúng vị trí phần trong bố cục. */
  mediaSlot: React.ReactNode;
  /** Khối Ví dụ. */
  viDuSlot: React.ReactNode;
}) {
  const [ds, setDs] = useState<CmsPhan[]>(banDau);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [gap, setGap] = useState<Record<string, boolean>>({});   // phần đang gập lại

  const luu = async (moi: CmsPhan[]) => {
    const cu = ds;
    setDs(moi);
    try {
      await cmsLuuBoCuc(topicId, moi.map((p) => ({ id: p.id, an: p.an })));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không lưu được bố cục");
      setDs(cu);   // không để UI nói dối là đã lưu
    }
  };
  const doi = (i: number, j: number) => {
    if (j < 0 || j >= ds.length) return;
    const moi = [...ds];
    [moi[i], moi[j]] = [moi[j], moi[i]];
    luu(moi);
  };
  const anHien = (i: number) => luu(ds.map((p, k) => (k === i ? { ...p, an: !p.an } : p)));

  const ai = async (phan: string) => {
    setBusy(phan); setErr(null);
    try {
      const r = await cmsAiPhan(topicId, phan);
      onDoi(COT[phan] ?? phan, r.html);
      toast("AI đã soạn nháp — rà lại rồi bấm Lưu");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
    } finally { setBusy(null); }
  };

  let dem = 0;
  const so = ds.map((p) => (p.an ? "–" : String(++dem)));

  return (
    <div className="esec">
      <div className="esec-h"><span className="n">📑</span> Nội dung bài học
        <span className="vz-ghi">{dem} phần đang hiện · số thứ tự học sinh thấy</span></div>
      {err && <div className="warn-box" style={{ marginBottom: 9 }}>⚠️ {err}</div>}

      {ds.map((p, i) => {
        const cot = COT[p.id];
        const co = !!(cot && giaTri[cot]?.trim());
        const dongLai = gap[p.id];
        return (
          <div className={"ps-o" + (p.id === "kien_thuc" ? " nb" : "") + (p.an ? " an" : "")} key={p.id}>
            <div className="ps-dau">
              <span className="ps-so tnum">{so[i]}</span>
              <span className="ps-em">{p.em}</span>
              <div className="ps-tx">
                <div className="ps-ten">{p.ten}
                  {p.an && <span className="ph-nhan">Đang ẩn</span>}
                  {!p.an && !co && !KHONG_HTML.has(p.id) && <span className="ps-trong">chưa soạn</span>}
                </div>
                <div className="ps-mo">{MO[p.id]}</div>
              </div>
              {!KHONG_HTML.has(p.id) && (
                <button className="ai-btn" type="button" disabled={busy === p.id}
                  onClick={() => ai(p.id)}>✨ {busy === p.id ? "Đang soạn…" : "AI hỗ trợ"}</button>
              )}
              <button className="ph-nut" type="button" disabled={i === 0}
                onClick={() => doi(i, i - 1)} aria-label="Lên">↑</button>
              <button className="ph-nut" type="button" disabled={i === ds.length - 1}
                onClick={() => doi(i, i + 1)} aria-label="Xuống">↓</button>
              <button className="ph-nut" type="button" onClick={() => anHien(i)}
                aria-pressed={p.an} title={p.an ? "Hiện phần này" : "Ẩn phần này"}>
                {p.an ? "🙈" : "👁"}</button>
              <button className="ph-nut" type="button" aria-expanded={!dongLai}
                onClick={() => setGap((g) => ({ ...g, [p.id]: !dongLai }))}
                title={dongLai ? "Mở ra soạn" : "Gập lại"}>{dongLai ? "▸" : "▾"}</button>
            </div>

            {/* Nội dung NẰM TRONG hàng của chính phần đó */}
            {!dongLai && (
              <div className="ps-than">
                {p.id === "minh_hoa" ? mediaSlot
                  : p.id === "vi_du" ? viDuSlot
                  : <SoanHtml value={giaTri[cot] ?? ""} onChange={(v) => onDoi(cot, v)}
                      placeholder={`Nội dung phần ${p.ten}…`} minHeight={p.id === "kien_thuc" ? 130 : 90} />}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
