import { useRef, useState } from "react";
import { ApiError, cmsSinhAnhViDu, cmsUploadAnhViDu } from "../api";
import type { CmsViDu } from "../types";

/** Câu chữ báo hiệu ví dụ PHẢI có hình mới đọc được.
 *
 *  AI được yêu cầu trả `anh_prompt` cho những ví dụ này, nhưng nội dung soạn
 *  trước khi có quy tắc đó (và ví dụ chuyên gia tự nhập) thì không có. Dò ngay
 *  trên đề bài để vẫn cảnh báo được — nếu không, người soạn phải tự đọc 47 ví dụ
 *  mới biết cái nào đang nhắc tới một cái hình không tồn tại. */
const DAU_HIEU = /hình bên|hình vẽ|hình sau|các hình|quan sát hình|hình dưới|xem hình/i;

export function canHinh(e: CmsViDu): boolean {
  return !e.anh && (!!e.anh_prompt || DAU_HIEU.test(e.de));
}

/** Hình của MỘT ví dụ: sinh bằng AI, hoặc tải ảnh chuyên gia tự vẽ/scan. */
export function AnhViDu({ topicId, chiSo, e, onDoi, toast }: {
  topicId: number;
  chiSo: number;
  e: CmsViDu;
  onDoi: (p: Partial<CmsViDu>) => void;
  toast: (m: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"" | "ai" | "up">("");
  const [err, setErr] = useState<string | null>(null);
  const [moTa, setMoTa] = useState(e.anh_prompt ?? "");
  const [suaMoTa, setSuaMoTa] = useState(false);

  const chay = async (viec: "ai" | "up", fn: () => Promise<{ anh: string; anh_xem: string }>) => {
    setBusy(viec); setErr(null);
    try {
      const r = await fn();
      // Server đã ghi thẳng vào DB; `anh_prompt` giữ lại để sinh lại nếu chưa vừa ý.
      onDoi({ anh: r.anh, anh_xem: r.anh_xem, anh_prompt: moTa.trim() || e.anh_prompt });
      toast("Đã có hình cho ví dụ " + (chiSo + 1));
      setSuaMoTa(false);
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Không lấy được hình");
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const anh = e.anh_xem || e.anh;

  return (
    <div className="vd-anh">
      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
        onChange={(ev) => {
          const f = ev.target.files?.[0];
          if (f) void chay("up", () => cmsUploadAnhViDu(topicId, chiSo, f));
        }} />

      {anh ? (
        <figure className="vd-hinh">
          <img src={anh} alt={`Hình ví dụ ${chiSo + 1}`} />
          <div className="vd-hinh-act">
            <button type="button" onClick={() => fileRef.current?.click()} disabled={!!busy}>
              {busy === "up" ? "Đang tải…" : "Đổi hình"}
            </button>
            {(e.anh_prompt || moTa.trim()) && (
              <button type="button" disabled={!!busy}
                onClick={() => void chay("ai", () => cmsSinhAnhViDu(topicId, chiSo, moTa))}>
                {busy === "ai" ? "Đang vẽ…" : "✨ Vẽ lại"}
              </button>
            )}
            <button type="button" className="bo" onClick={() => onDoi({ anh: "", anh_xem: "" })}
              disabled={!!busy}>Bỏ hình</button>
          </div>
        </figure>
      ) : (
        <div className={"vd-thieu" + (canHinh(e) ? " canh" : "")}>
          <span className="vd-tt">
            {canHinh(e) ? "⚠️ Ví dụ này nhắc tới hình vẽ mà chưa có hình" : "Chưa có hình (không bắt buộc)"}
          </span>
          <div className="vd-hinh-act">
            <button type="button" onClick={() => fileRef.current?.click()} disabled={!!busy}>
              {busy === "up" ? "Đang tải…" : "⬆️ Tải hình"}
            </button>
            <button type="button" disabled={!!busy}
              onClick={() => {
                // Chưa có mô tả thì mở ô nhập: sinh ảnh mù không ra hình đúng.
                if (!moTa.trim()) { setSuaMoTa(true); return; }
                void chay("ai", () => cmsSinhAnhViDu(topicId, chiSo, moTa));
              }}>
              {busy === "ai" ? "Đang vẽ…" : "✨ Vẽ bằng AI"}
            </button>
          </div>
        </div>
      )}

      {(suaMoTa || (!anh && moTa.trim() && canHinh(e))) && (
        <div className="vd-mota">
          <label>Mô tả hình cần vẽ (tiếng Anh cho ra hình sát nhất)</label>
          <textarea value={moTa} rows={2} onChange={(ev) => setMoTa(ev.target.value)}
            placeholder="equilateral triangle, parallelogram and circle side by side, flat textbook style, no text" />
        </div>
      )}
      {err && <div className="vd-loi">{err}</div>}
    </div>
  );
}
