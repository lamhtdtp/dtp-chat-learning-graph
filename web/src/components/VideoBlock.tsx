import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../config";
import { getVideoStatus } from "../api";
import type { VideoInfo } from "../types";

// Video là BỔ SUNG: hiện dưới câu trả lời khi sẵn sàng. Trong lúc worker dựng,
// hiện placeholder "đang tạo" + poll trạng thái; lỗi -> báo nhẹ, không phá UX
// (US-16 Scenario 4).
export function VideoBlock({ info }: { info: VideoInfo }) {
  const [status, setStatus] = useState(info.status);
  const [url, setUrl] = useState(info.video_url);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (status === "DONE" || status === "FAILED") return;
    let alive = true;
    const poll = async () => {
      try {
        const s = await getVideoStatus(info.job_id);
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
  }, [info.job_id, status]);

  if (status === "DONE" && url) {
    return (
      <div className="video-block">
        <div className="video-label">🎬 Video minh hoạ</div>
        <video className="video-player" controls preload="metadata" src={`${API_BASE}${url}`} />
      </div>
    );
  }
  if (status === "FAILED") {
    return <div className="video-block muted">🎬 Video minh hoạ chưa sẵn sàng.</div>;
  }
  return (
    <div className="video-block pending">
      <span className="video-spin" /> Đang tạo video minh hoạ…
    </div>
  );
}
