import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../config";
import { generateVideo, getVideoStatus } from "../api";
import type { VideoInfo } from "../types";

// Video sinh ON-DEMAND: câu hỏi đủ điều kiện -> hiện nút "Tạo video minh hoạ".
// Học sinh bấm mới sinh (tránh chờ nếu không cần). Đã có sẵn (cache) thì hiện
// player ngay, không cần bấm.
export function VideoBlock({ info }: { info: VideoInfo }) {
  const [status, setStatus] = useState(info.status);
  const [jobId, setJobId] = useState<number | null>(info.job_id ?? null);
  const [url, setUrl] = useState(info.video_url);
  const [err, setErr] = useState<string | null>(null);
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

  if (status === "DONE" && url) {
    return (
      <div className="video-block">
        <div className="video-label">🎬 Video minh hoạ</div>
        <video className="video-player" controls preload="metadata" src={`${API_BASE}${url}`} />
      </div>
    );
  }
  if (status === "OFFERED") {
    return (
      <div className="video-block">
        <button className="video-btn" type="button" onClick={onCreate}>🎬 Tạo video minh hoạ</button>
        {err && <span className="video-err">{err}</span>}
      </div>
    );
  }
  if (status === "FAILED") {
    return <div className="video-block muted">🎬 Chưa tạo được video, bạn thử lại sau nhé.</div>;
  }
  return (
    <div className="video-block pending">
      <span className="video-spin" /> Đang tạo video minh hoạ…
    </div>
  );
}
