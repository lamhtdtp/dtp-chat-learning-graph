import { API_BASE } from "../config";
import type { Citation } from "../types";

// Modal xem ảnh trang SGK gốc khi bấm chip trích dẫn.
export function BookPageModal({ cite, onClose }: { cite: Citation; onClose: () => void }) {
  const src = `${API_BASE}/books/pages/${cite.tap}/${cite.page_no}`;
  const label =
    `Trang ${cite.page_no}` +
    (cite.tap ? ` · Tập ${cite.tap}` : "") +
    (cite.bai_so ? ` · Bài ${cite.bai_so}` : "");

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>📖 {label}</span>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Đóng">✕</button>
        </div>
        <div className="modal-body">
          <img src={src} alt={label} />
        </div>
      </div>
    </div>
  );
}
