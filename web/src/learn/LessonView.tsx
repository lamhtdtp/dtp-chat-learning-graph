import { useState } from "react";
import type { Lesson, MinhHoa, QuizResult } from "../types";
import { renderMath } from "../mathHtml";
import { QuizView } from "./QuizView";

function Media({ m }: { m: MinhHoa }) {
  const isVideo = m.type === "video";
  const cap = m.caption || (isVideo ? "Video minh hoạ" : "Hình minh hoạ");
  if (isVideo && m.url) {
    return (
      <figure>
        <video className="img-poster" style={{ minHeight: 156 }} controls src={m.url} />
        <figcaption>{cap}{m.source === "ai" && " · AI tự sinh"}</figcaption>
      </figure>
    );
  }
  return (
    <figure>
      {isVideo ? (
        <div className="poster">
          <div className="formula">n = p × q ?</div>
          <div className="play" aria-hidden>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
          </div>
          <span className="vlabel">30–90 giây</span>
        </div>
      ) : m.url ? (
        <div className="img-poster"><img src={m.url} alt={cap} /></div>
      ) : (
        <div className="img-poster" aria-hidden>🖼️</div>
      )}
      <figcaption>{cap}{m.source === "ai" && " · AI tự sinh"}</figcaption>
    </figure>
  );
}

const SUGGESTS = [
  "Giải thích lại phần khái niệm dễ hiểu hơn",
  "Cho mình thêm một ví dụ",
  "Phần này học sinh hay nhầm chỗ nào?",
];

export function LessonView({ lesson, teacher, onMarkDone, onQuizGraded, onAsk }: {
  lesson: Lesson; teacher: boolean; onMarkDone?: () => void;
  onQuizGraded?: (r: QuizResult) => void; onAsk?: (q: string) => void;
}) {
  const [showQuiz, setShowQuiz] = useState(false);
  const gy = (teacher && lesson.day?.goi_y) || {};
  const chuaSoan = lesson.trang_thai === "chua_bien_soan";

  if (chuaSoan) {
    return (
      <article className="lesson">
        <span className="eyebrow">Chưa biên soạn</span>
        <h1>{lesson.dv}</h1>
        <p className="lead">Nội dung đơn vị này đang được chuyên gia biên soạn. Quay lại sau nhé!</p>
      </article>
    );
  }

  return (
    <article className="lesson">
      <span className="eyebrow">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M4 5h11a2 2 0 012 2v12M4 5v13a1 1 0 001 1h12M4 5a2 2 0 00-2 2v11" /></svg>
        {teacher ? "Chế độ giáo viên" : "Đang học"}
      </span>
      <h1>{lesson.dv}</h1>

      {/* ① Khái niệm (HTML chuyên gia; blockquote -> callout; $…$ -> KaTeX) */}
      {lesson.khai_niem
        ? <div dangerouslySetInnerHTML={{ __html: renderMath(lesson.khai_niem) }} />
        : <p className="lead">Chưa có nội dung khái niệm.</p>}

      {/* Hướng dẫn giảng dạy (GV) */}
      {teacher && lesson.day && (lesson.day.muc_tieu || lesson.day.thoi_luong || lesson.day.luu_y) && (
        <div className="callout">
          <b>🎓 Hướng dẫn giảng dạy.</b>{" "}
          {lesson.day.muc_tieu && <> <b>Mục tiêu:</b> {lesson.day.muc_tieu} </>}
          {lesson.day.thoi_luong && <> · <b>Thời lượng:</b> {lesson.day.thoi_luong} </>}
          {lesson.day.luu_y && <> · <b>Lưu ý:</b> {lesson.day.luu_y}</>}
        </div>
      )}

      {/* ② Minh hoạ */}
      {lesson.minh_hoa.length > 0 && (
        <>
          <h3><span className="hi">🎬</span> Minh hoạ</h3>
          <div className="media">{lesson.minh_hoa.map((m, i) => <Media key={i} m={m} />)}</div>
          {gy.minh_hoa && <div className="media-note">🎓 {gy.minh_hoa}</div>}
        </>
      )}

      {/* ③ Ví dụ */}
      {lesson.vi_du.length > 0 && (
        <>
          <h3><span className="hi">✏️</span> Ví dụ</h3>
          {lesson.vi_du.map((e, i) => (
            <div className="vd" key={i}>
              <div className="q" dangerouslySetInnerHTML={{ __html: renderMath(e.de) }} />
              <div className="a" dangerouslySetInnerHTML={{ __html: renderMath(e.giai) }} />
            </div>
          ))}
          {gy.vi_du && <div className="media-note">🎓 {gy.vi_du}</div>}
        </>
      )}

      <div className="divider" />

      {/* ④ Kiểm tra nhanh */}
      {lesson.co_quiz && lesson.quiz.length > 0 ? (
        showQuiz ? (
          <>
            <h3><span className="hi">✅</span> Bài kiểm tra nhanh</h3>
            <QuizView topicId={lesson.topic_id} quiz={lesson.quiz} onGraded={onQuizGraded} />
          </>
        ) : (
          <div className="exercise-cta">
            <button className="btn btn-primary" type="button" onClick={() => setShowQuiz(true)}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6"><path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" /></svg>
              Làm bài kiểm tra nhanh
            </button>
            <div className="cta-hint">{lesson.quiz.length} câu sinh tự động theo ma trận đặc tả</div>
          </div>
        )
      ) : (
        <div className="exercise-cta">
          {!teacher && onMarkDone
            ? <>
                <button className="btn btn-primary" type="button" onClick={onMarkDone}>✓ Đánh dấu đã hoàn thành</button>
                <div className="cta-hint">Đơn vị này chưa có bài kiểm tra nhanh</div>
              </>
            : <div className="cta-hint">Chưa có bài kiểm tra nhanh cho đơn vị này.</div>}
        </div>
      )}

      {onAsk && (
        <div className="suggest">
          <div className="s-label">✨ Chưa rõ chỗ nào? Hỏi trợ lý thử:</div>
          <div className="chips">
            {SUGGESTS.map((q) => (
              <button className="chip" type="button" key={q} onClick={() => onAsk(q)}>💬 {q}</button>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
