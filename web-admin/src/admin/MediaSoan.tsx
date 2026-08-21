import { useRef, useState } from "react";
import { ApiError, cmsUploadAnh, cmsUploadVideo } from "../api";
import type { CmsMedia } from "../types";

const NHAN_NGUON: Record<string, string> = { expert: "chuyên gia", ai: "AI" };

/** Khu Minh hoạ: MỘT vùng kéo-thả nhận cả ảnh lẫn video + lưới thumbnail.
 *
 *  Trước đây: nút "＋ Thêm ảnh/URL" đẻ ra một hàng hai ô text (phải tự đi tìm URL
 *  ở đâu đó dán vào), và một nút "⬆️ Video" riêng. Chuyên gia có ảnh trong máy thì
 *  không có đường nào đưa vào.
 */
export function MediaSoan({ topicId, ds, onDoi, toast }: {
  topicId: number;
  ds: CmsMedia[];
  onDoi: (moi: CmsMedia[]) => void;
  toast: (m: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [keo, setKeo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [urlMo, setUrlMo] = useState(false);
  const [url, setUrl] = useState("");

  const nap = async (fs: FileList | File[] | null) => {
    const list = Array.from(fs ?? []);
    if (!list.length) return;
    setBusy(true); setErr(null);
    try {
      let cuoi: CmsMedia[] = ds;
      for (const f of list) {
        // Phân loại theo MIME chứ không theo đuôi tên: file .mp4 đổi tên thành
        // .png vẫn phải đi đúng đường video.
        const r = f.type.startsWith("video/")
          ? await cmsUploadVideo(topicId, f, f.name)
          : await cmsUploadAnh(topicId, f, f.name);
        cuoi = r.minh_hoa;
      }
      onDoi(cuoi);
      toast(`Đã tải ${list.length} tệp`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Không tải được tệp");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const themUrl = () => {
    const u = url.trim();
    if (!u) return;
    const laVideo = /\.(mp4|webm|mov)(\?|$)/i.test(u);
    onDoi([...ds, { type: laVideo ? "video" : "image", url: u,
                    caption: "", source: "expert" }]);
    setUrl(""); setUrlMo(false);
  };
  const sua = (i: number, p: Partial<CmsMedia>) =>
    onDoi(ds.map((m, j) => (j === i ? { ...m, ...p } : m)));
  const bo = (i: number) => onDoi(ds.filter((_, j) => j !== i));

  return (
    <>
      {err && <div className="warn-box" style={{ marginBottom: 10 }}>⚠️ {err}</div>}

      <div className={"mz" + (keo ? " keo" : "") + (busy ? " busy" : "")}
        onClick={() => !busy && fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setKeo(true); }}
        onDragLeave={() => setKeo(false)}
        onDrop={(e) => { e.preventDefault(); setKeo(false); nap(e.dataTransfer.files); }}>
        <span className="mz-em">{busy ? "⏳" : "🖼️"}</span>
        <div>
          <b>{busy ? "Đang tải lên…" : "Kéo ảnh hoặc video vào đây"}</b>
          <div className="mz-mo">PNG · JPG · WEBP (≤8MB) · MP4 · WEBM · MOV (≤100MB)</div>
        </div>
        <input ref={fileRef} type="file" multiple hidden
          accept="image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime"
          onChange={(e) => nap(e.target.files)} />
      </div>

      <div className="mz-phu">
        <button className="act txt" type="button" onClick={() => setUrlMo((v) => !v)}>
          🔗 Dán URL bên ngoài
        </button>
        {ds.length > 0 && <span className="badge-man">{ds.length} tệp minh hoạ</span>}
      </div>
      {urlMo && (
        <div className="mz-url">
          <input type="text" value={url} placeholder="https://… (ảnh hoặc mp4)"
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); themUrl(); } }} />
          <button className="act txt" type="button" onClick={themUrl}>Thêm</button>
        </div>
      )}

      {/* Lưới thumbnail: thấy ngay mình đang có gì thay vì đọc danh sách URL */}
      {ds.length > 0 && (
        <div className="mzg">
          {ds.map((m, i) => (
            <div className="mzi" key={i}>
              <div className="mzi-xem">
                {m.type === "video"
                  ? (m.url_xem
                    ? <video src={m.url_xem} muted playsInline
                        controlsList="nodownload" onContextMenu={(e) => e.preventDefault()} />
                    : <span className="mzi-cho">⏳ video đang dựng</span>)
                  : (m.url_xem || m.url)
                    ? <img src={m.url_xem || m.url || ""} alt={m.caption || ""} />
                    : <span className="mzi-cho">🖼️</span>}
                <span className="mzi-loai">{m.type === "video" ? "🎬" : "🖼️"}</span>
                {m.source && <span className="mzi-ng">{NHAN_NGUON[m.source] ?? m.source}</span>}
                <button className="mzi-bo" type="button" title="Bỏ tệp này"
                  onClick={() => bo(i)}>✕</button>
              </div>
              <input className="mzi-cap" type="text" value={m.caption ?? ""}
                placeholder="Chú thích (học sinh đọc được)"
                onChange={(e) => sua(i, { caption: e.target.value })} />
            </div>
          ))}
        </div>
      )}
    </>
  );
}
