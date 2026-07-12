import { useEffect, useState } from "react";
import { API_BASE } from "../config";
import { getBookPageUrl } from "../api";
import type { Citation } from "../types";

// Modal xem ảnh trang SGK gốc khi bấm chip trích dẫn. Ảnh được bảo vệ bằng URL
// KÝ có hạn: xin link ký (Bearer) khi mở modal rồi mới gán vào <img>.
export function BookPageModal({ cite, onClose }: { cite: Citation; onClose: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  const label =
    `Trang ${cite.page_no}` +
    (cite.tap ? ` · Tập ${cite.tap}` : "") +
    (cite.bai_so ? ` · Bài ${cite.bai_so}` : "");

  useEffect(() => {
    let alive = true;
    if (cite.tap == null) {
      setErr(true);
      return;
    }
    getBookPageUrl(cite.tap, cite.page_no)
      .then((r) => alive && setSrc(`${API_BASE}${r.url}`))
      .catch(() => alive && setErr(true));
    return () => {
      alive = false;
    };
  }, [cite]);

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>📖 {label}</span>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Đóng">✕</button>
        </div>
        <div className="modal-body">
          {err ? (
            <div className="book-msg">Không tải được ảnh trang.</div>
          ) : src ? (
            <img src={src} alt={label} draggable={false} onContextMenu={(e) => e.preventDefault()} />
          ) : (
            <div className="book-msg">Đang tải…</div>
          )}
        </div>
      </div>
    </div>
  );
}
