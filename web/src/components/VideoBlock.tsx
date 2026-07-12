import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../config";
import { generateVideo, getVideoStatus } from "../api";
import type { VideoInfo } from "../types";

// Video sinh ON-DEMAND. Trong bong bóng trả lời chỉ hiện 1 nút; bấm mở POPUP:
// - OFFERED  -> bấm "Tạo video" thì sinh + mở popup xem tiến trình rồi player.
// - DONE     -> bấm "Xem video" mở popup phát ngay (đã cache).
// Học sinh bấm mới sinh (tránh chờ nếu không cần).
export function VideoBlock({ info }: { info: VideoInfo }) {
  const [status, setStatus] = useState(info.status);
  const [jobId, setJobId] = useState<number | null>(info.job_id ?? null);
  const [url, setUrl] = useState(info.video_url);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);

  // Poll trạng thái khi job đang chạy (QUEUED/RENDERING).
  useEffect(() => {
    if (jobId == null || status === "DONE" || status === "FAILED" || status === "OFFERED") return;
    let alive = true;
    const poll = async () => {
      try {
        const s = await getVideoStatus(jobId);
        if (!alive) return;
        setStatus(s.status);
        setUrl(s.video_url);
        if (s.status !== "DONE" && s.status !== "FAILED") {
          timer.current = window.setTimeout(poll, 3000);
        }
      } catch {
        if (alive) timer.current = window.setTimeout(poll, 5000);
      }
    };
    timer.current = window.setTimeout(poll, 2500);
    return () => {
      alive = false;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [jobId, status]);

  const onCreate = async () => {
    if (!info.concept_key) return;
    setErr(null);
    setOpen(true);
    setStatus("QUEUED");
    try {
      const s = await generateVideo(info.concept_key);
      setJobId(s.job_id ?? null);
      setStatus(s.status);
      setUrl(s.video_url);
    } catch {
      setStatus("OFFERED");
      setErr("Không tạo được video, thử lại nhé.");
    }
  };

  // Nút trong bong bóng theo trạng thái.
  const trigger =
    status === "DONE" && url ? (
      <button className="video-btn" type="button" onClick={() => setOpen(true)}>🎬 Xem video minh hoạ</button>
    ) : status === "OFFERED" ? (
      <button className="video-btn" type="button" onClick={onCreate}>🎬 Tạo video minh hoạ</button>
    ) : status === "FAILED" ? (
      <button className="video-btn" type="button" onClick={() => setOpen(true)}>🎬 Video minh hoạ (xem chi tiết)</button>
    ) : (
      <button className="video-btn" type="button" onClick={() => setOpen(true)}>🎬 Đang tạo video…</button>
    );

  return (
    <>
      <div className="video-block">
        {trigger}
        {err && !open && <span className="video-err">{err}</span>}
      </div>

      {open && (
        <div className="modal-scrim" onClick={() => setOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <span>🎬 Video minh hoạ</span>
              <button className="modal-close" onClick={() => setOpen(false)} type="button" aria-label="Đóng">✕</button>
            </div>
            <div className="modal-body">
              {status === "DONE" && url && (
                <video
                  className="video-player"
                  controls
                  autoPlay
                  preload="metadata"
                  src={`${API_BASE}${url}`}
                  controlsList="nodownload noremoteplayback noplaybackrate"
                  disablePictureInPicture
                  onContextMenu={(e) => e.preventDefault()}
                />
              )}
              {(status === "QUEUED" || status === "RENDERING") && (
                <div className="video-block pending"><span className="video-spin" /> Đang tạo video minh hoạ…</div>
              )}
              {status === "FAILED" && (
                <div className="video-block muted">🎬 Chưa tạo được video, bạn thử lại sau nhé.</div>
              )}
              {status === "OFFERED" && (
                <div className="video-modal-offer">
                  <button className="video-btn" type="button" onClick={onCreate}>🎬 Tạo video minh hoạ</button>
                  {err && <span className="video-err">{err}</span>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
