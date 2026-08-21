import { useState } from "react";
import { ApiError, cmsAiPhan, cmsLuuBoCuc } from "../api";
import type { CmsPhan } from "../types";

const MO: Record<string, string> = {
  khoi_dong: "Dẫn vào bài, gợi tò mò — không dạy kiến thức mới",
  hoat_dong: "Học sinh tự làm để tự phát hiện ra kiến thức",
  kien_thuc: "Định nghĩa, tính chất cốt lõi — phần bắt buộc",
  minh_hoa: "Ảnh và video minh hoạ (sinh ở trình soạn)",
  vi_du: "Ví dụ có lời giải từng bước (sinh ở trình soạn)",
  luyen_tap: "Bài từ nhận biết đến vận dụng, có đáp số",
  bai_tap: "Bài về nhà, không kèm lời giải",
};
// Hai phần này sinh bằng "✨ Gợi ý AI" ở trình soạn (kèm ảnh/video), không qua
// đường AI-theo-phần — nên ẩn nút để không dẫn người dùng vào lỗi 400.
const KHONG_AI = new Set(["minh_hoa", "vi_du"]);

/** Danh sách 7 phần: đổi thứ tự · ẩn/hiện · AI hỗ trợ theo từng phần (REQ §2.2).
 *
 *  Số thứ tự hiện ở đây tính theo CÁC PHẦN ĐANG HIỆN, giống hệt phía học sinh —
 *  chuyên gia phải thấy đúng con số học sinh sẽ thấy, không thì ẩn/hiện thành đoán.
 */
export function BoCucPhan({ topicId, banDau, onAi, toast }: {
  topicId: number;
  banDau: CmsPhan[];
  /** Nhận HTML nháp AI cho một phần -> trình soạn đổ vào ô tương ứng. */
  onAi: (phan: string, html: string) => void;
  toast: (m: string) => void;
}) {
  const [ds, setDs] = useState<CmsPhan[]>(banDau);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const luu = async (moi: CmsPhan[]) => {
    setDs(moi);   // cập nhật ngay, không đợi mạng — bấm ↑↓ phải thấy liền
    try {
      await cmsLuuBoCuc(topicId, moi.map((p) => ({ id: p.id, an: p.an })));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không lưu được bố cục");
      setDs(ds);  // trả về trạng thái cũ, không để UI nói dối là đã lưu
    }
  };

  const doi = (i: number, j: number) => {
    if (j < 0 || j >= ds.length) return;
    const moi = [...ds];
    [moi[i], moi[j]] = [moi[j], moi[i]];
    luu(moi);
  };
  const anHien = (i: number) =>
    luu(ds.map((p, k) => (k === i ? { ...p, an: !p.an } : p)));

  const ai = async (phan: string) => {
    setBusy(phan); setErr(null);
    try {
      const r = await cmsAiPhan(topicId, phan);
      onAi(phan, r.html);
      toast("AI đã soạn nháp — rà lại rồi bấm Lưu");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
    } finally { setBusy(null); }
  };

  // Số thứ tự chỉ đếm phần ĐANG HIỆN; phần ẩn hiện dấu "–".
  let dem = 0;
  const so = ds.map((p) => (p.an ? "–" : String(++dem)));

  return (
    <div className="esec">
      <div className="esec-h"><span className="n">📑</span> Bố cục 7 phần
        <span className="vz-ghi">{dem} phần đang hiện · số thứ tự học sinh thấy</span></div>
      {err && <div className="warn-box" style={{ marginBottom: 9 }}>⚠️ {err}</div>}
      {ds.map((p, i) => (
        <div className={"ph-o" + (p.id === "kien_thuc" ? " nb" : "") + (p.an ? " an" : "")} key={p.id}>
          <span className="ph-so tnum">{so[i]}</span>
          <span className="ph-em">{p.em}</span>
          <div className="ph-tx">
            <div className="ph-ten">{p.ten}
              {p.an && <span className="ph-nhan">Đang ẩn</span>}</div>
            <div className="ph-mo">{MO[p.id]}</div>
          </div>
          {!KHONG_AI.has(p.id) && (
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
        </div>
      ))}
    </div>
  );
}
