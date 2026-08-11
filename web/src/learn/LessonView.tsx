import { useState } from "react";
import type { Lesson, MinhHoa, Neo, QuizResult } from "../types";
import { renderMath } from "../mathHtml";
import { QuizView } from "./QuizView";
import { TroLyCard } from "./TroLyCard";
import { useMocDoc } from "./useMocDoc";

// Học sinh tắt gợi ý chủ động -> nhớ máy này, không hỏi lại mỗi bài.
const KHOA_TAT_NHAC = "tat_nhac_chu_dong";

function Media({ m }: { m: MinhHoa }) {
  const isVideo = m.type === "video";
  const cap = m.caption || (isVideo ? "Video minh hoạ" : "Hình minh hoạ");
  if (isVideo && m.url) {
    return (
      <figure>
        {/* Hạn chế tải video về: controlsList bỏ nút Tải xuống trong thanh điều
            khiển (Chrome/Edge), chặn menu chuột phải "Lưu video". KHÔNG phải bảo
            vệ tuyệt đối — link đã ký vẫn mở được trực tiếp trong 12 giờ. */}
        <video className="img-poster" style={{ minHeight: 156 }} controls src={m.url}
          controlsList="nodownload noplaybackrate" disablePictureInPicture
          onContextMenu={(e) => e.preventDefault()} />
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
    </figure>
  );
}

const SUGGESTS = [
  "Giải thích lại phần khái niệm dễ hiểu hơn",
  "Cho mình thêm một ví dụ",
  "Phần này học sinh hay nhầm chỗ nào?",
];

/** Câu hỏi mở đầu khi bấm "Hỏi về đoạn này" — tự nhiên hơn là mở thẻ trống rồi
 *  bắt học sinh nghĩ ra câu hỏi. */
const CAU_MO: Record<string, string> = {
  khai_niem: "Giải thích lại phần khái niệm này dễ hiểu hơn giúp mình",
  minh_hoa: "Phần minh hoạ này đang nói về điều gì?",
};
const cauMoViDu = (i: number) => `Ví dụ ${i + 1}: giải thích từng bước giúp mình`;

export function LessonView({ lesson, teacher, onMarkDone, onQuizGraded }: {
  lesson: Lesson; teacher: boolean; onMarkDone?: () => void;
  onQuizGraded?: (r: QuizResult) => void;
}) {
  const [showQuiz, setShowQuiz] = useState(false);
  // Thẻ trợ lý, khoá theo neo. State nằm ở ĐÂY chứ không ở LearnApp: đổi bài là
  // component unmount nên thẻ tự dọn — đúng hành vi mong muốn.
  // Đóng thẻ chỉ đặt `an`, KHÔNG xoá: mở lại từ thanh "Đã hỏi" phải còn nguyên
  // hội thoại, chứ bắt hỏi lại là mất thêm một lượt của học sinh.
  type Muc = { neo: Neo | null; nhan: string; hoi: string; an?: boolean };
  const [the, setThe] = useState<Record<string, Muc>>({});
  const [moLichSu, setMoLichSu] = useState(false);

  const moThe = (k: string, m: Muc) =>
    setThe((t) => ({ ...t, [k]: t[k] ? { ...t[k], an: false } : m }));
  const dongThe = (k: string) => setThe((t) => ({ ...t, [k]: { ...t[k], an: true } }));
  const toiThe = (k: string) => {
    moThe(k, the[k]);
    setMoLichSu(false);
    // Đợi bỏ class `an` xong mới cuộn — display:none thì phần tử chưa có vị trí.
    requestAnimationFrame(() =>
      document.getElementById(`tl-${k}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  };
  const daHoi = Object.entries(the);

  const NutHoi = ({ neo, nhan, hoi, ngan }: { neo: Neo; nhan: string; hoi: string; ngan?: boolean }) => (
    <button className="hoi-doan" type="button" onClick={() => moThe(neo, { neo, nhan, hoi })}
      title={`Hỏi trợ lý về ${nhan.toLowerCase()}`}>
      💬 {ngan ? "Hỏi" : "Hỏi về đoạn này"}
    </button>
  );

  const The = ({ k }: { k: string }) => {
    const t = the[k];
    if (!t) return null;
    return (
      <div id={`tl-${k}`}>
        <TroLyCard topicId={lesson.topic_id} anchor={t.neo} nhan={t.nhan} hoiDau={t.hoi}
          an={t.an} onDong={() => dongThe(k)} />
      </div>
    );
  };

  // ── Trợ lý CHỦ ĐỘNG ở mốc "đọc xong khái niệm" (lát 4) ────────────────────
  // Nội dung đã sinh sẵn lúc biên soạn (topic_content.nhac_json) nên bấm chọn là
  // có phản hồi ngay: KHÔNG gọi LLM, KHÔNG trừ lượt hỏi trong ngày.
  const [tatNhac, setTatNhac] = useState(() => localStorage.getItem(KHOA_TAT_NHAC) === "1");
  const nhacKN = lesson.nhac?.find((n) => n.moc === "khai_niem") ?? null;
  const moc = useMocDoc(!!nhacKN && !tatNhac && !teacher);
  const tatHan = () => { localStorage.setItem(KHOA_TAT_NHAC, "1"); setTatNhac(true); };

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
      {lesson.khai_niem && (
        <h3><span className="hi">💡</span> Khái niệm
          <NutHoi neo="khai_niem" nhan="Khái niệm" hoi={CAU_MO.khai_niem} />
        </h3>
      )}
      {/* ref bọc CHÍNH khối nội dung (không phải một thẻ mốc rỗng cao 0px) —
          useMocDoc đo theo rect của khối này. */}
      {lesson.khai_niem
        ? <div ref={moc.ref} dangerouslySetInnerHTML={{ __html: renderMath(lesson.khai_niem) }} />
        : <p className="lead">Chưa có nội dung khái niệm.</p>}
      <The k="khai_niem" />

      {moc.xong && nhacKN && !tatNhac && (
        <div className="nhac-boc">
          <TroLyCard topicId={lesson.topic_id} anchor="khai_niem" nhan="Khái niệm" chuDong
            noiDungSan={`<p>Bạn vừa đọc xong phần khái niệm — thử nhanh một câu nhé:</p><p><b>${renderMath(nhacKN.hoi)}</b></p>`}
            nguonSan="Khái niệm"
            dapNhanh={nhacKN.dap.map((d, i) => ({
              t: d,
              tra: (i === nhacKN.dung
                ? "<p>🎉 Chính xác!</p>"
                // Phương án thường đã tự kết bằng dấu chấm -> cắt đi, không thì
                // ra "…không thuộc N*.." ngay giữa câu phản hồi.
                : `<p>Chưa đúng rồi — đáp án đúng là <b>${renderMath((nhacKN.dap[nhacKN.dung] ?? "").replace(/\s*[.!?]+\s*$/, ""))}</b>.</p>`)
                + (nhacKN.giai ? `<p>${renderMath(nhacKN.giai)}</p>` : ""),
            }))}
            onDong={() => setTatNhac(true)} />
          <button className="nhac-tat" type="button" onClick={tatHan}>
            🔕 Đừng gợi ý kiểu này nữa
          </button>
        </div>
      )}

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
          <h3><span className="hi">🎬</span> Minh hoạ
            <NutHoi neo="minh_hoa" nhan="Minh hoạ" hoi={CAU_MO.minh_hoa} />
          </h3>
          <div className="media">{lesson.minh_hoa.map((m, i) => <Media key={i} m={m} />)}</div>
          {gy.minh_hoa && <div className="media-note">🎓 {gy.minh_hoa}</div>}
          <The k="minh_hoa" />
        </>
      )}

      {/* ③ Ví dụ — mỗi ví dụ hỏi riêng được, trả lời nở ra ngay dưới nó */}
      {lesson.vi_du.length > 0 && (
        <>
          <h3><span className="hi">✏️</span> Ví dụ</h3>
          {lesson.vi_du.map((e, i) => {
            const neo = `vi_du:${i + 1}` as Neo;
            return (
              <div key={i}>
                <div className="vd">
                  <div className="vd-top">
                    <div className="q" dangerouslySetInnerHTML={{ __html: renderMath(e.de) }} />
                    <NutHoi neo={neo} nhan={`Ví dụ ${i + 1}`} hoi={cauMoViDu(i)} ngan />
                  </div>
                  <div className="a" dangerouslySetInnerHTML={{ __html: renderMath(e.giai) }} />
                </div>
                <The k={neo} />
              </div>
            );
          })}
          {gy.vi_du && <div className="media-note">🎓 {gy.vi_du}</div>}
        </>
      )}

      {/* Hỏi chung cả bài — neo null, backend ghép khái niệm + ví dụ (không quiz).
          Đặt TRƯỚC bài kiểm tra: gỡ rối xong mới thi. Trước đây chip gợi ý nằm
          dưới bài kiểm tra, hoá ra hỏi "chưa rõ chỗ nào?" sau khi các em đã nộp. */}
      <div className="suggest">
        <div className="s-label">✨ Chưa rõ chỗ nào trong bài <b>{lesson.dv}</b>? Hỏi thử:</div>
        <div className="chips">
          {SUGGESTS.map((q) => (
            <button className="chip" type="button" key={q}
              onClick={() => moThe("toan_bai", { neo: null, nhan: "Toàn bài", hoi: q })}>💬 {q}</button>
          ))}
        </div>
        <The k="toan_bai" />
      </div>

      <div className="divider" />

      {/* ④ Kiểm tra nhanh — CHỐT CUỐI của bài, nằm dưới cùng */}
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

      {/* Bù cho việc bỏ cột chat: nơi xem lại mọi câu đã hỏi trong bài. Thẻ đóng
          rồi vẫn còn ở đây và mở lại được nguyên hội thoại. */}
      {daHoi.length > 0 && (
        <div className={"da-hoi" + (moLichSu ? " mo" : "")}>
          {moLichSu && (
            <div className="dh-list">
              {daHoi.map(([k, t]) => (
                <button type="button" key={k} onClick={() => toiThe(k)}>
                  <span className="dh-neo">{t.nhan}</span>
                  <span className="dh-q">{t.hoi}</span>
                </button>
              ))}
            </div>
          )}
          <button className="dh-nut" type="button" onClick={() => setMoLichSu((v) => !v)}
            aria-expanded={moLichSu}>
            💬 Đã hỏi ({daHoi.length}) {moLichSu ? "▾" : "▴"}
          </button>
        </div>
      )}
    </article>
  );
}
