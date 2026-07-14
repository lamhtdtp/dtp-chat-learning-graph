import { useEffect, useState } from "react";
import { API_BASE } from "../config";
import { getBookPageSummary, getBookPageUrl } from "../api";
import { Portal } from "./Portal";
import type { Citation } from "../types";

// Modal xem ảnh trang SGK gốc khi bấm chip trích dẫn. Ảnh được bảo vệ bằng URL
// KÝ có hạn: xin link ký (Bearer) khi mở modal rồi mới gán vào <img>.
export function BookPageModal({ cite, mon = "toan", onClose }: { cite: Citation; mon?: string; onClose: () => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  // Tóm tắt trang (lazy): "loading" -> chuỗi tóm tắt | null (không có).
  const [summary, setSummary] = useState<string | null | "loading">("loading");

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
    getBookPageUrl(cite.tap, cite.page_no, mon)
      .then((r) => alive && setSrc(`${API_BASE}${r.url}`))
      .catch(() => alive && setErr(true));
    setSummary("loading");
    getBookPageSummary(cite.tap, cite.page_no, mon)
      .then((r) => alive && setSummary(r.summary))
      .catch(() => alive && setSummary(null));
    return () => {
      alive = false;
    };
  }, [cite, mon]);

  return (
    <Portal>
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span>📖 {label}</span>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Đóng">✕</button>
        </div>
        <div className="modal-body">
          <div className="book-summary">
            <div className="book-summary-head">📝 Tóm tắt trang</div>
            {summary === "loading"
              ? <div className="book-summary-loading">Đang tóm tắt…</div>
              : summary
                ? <p>{summary}</p>
                : <div className="book-summary-loading">Chưa có tóm tắt cho trang này.</div>}
          </div>
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
    </Portal>
  );
}
