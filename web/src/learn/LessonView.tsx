import { useState } from "react";
import type { Lesson, MinhHoa, Neo, PhanBoCuc, QuizResult } from "../types";
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
        <figcaption>{cap}</figcaption>
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
      {/* `cap` trước đây chỉ dùng cho alt — không ai đọc được nó. Mockup ghi rõ
          caption nằm dưới mỗi thẻ media. */}
      <figcaption>{cap}</figcaption>
    </figure>
  );
}

// Thứ tự chuẩn 7 phần — CHỈ dùng khi server không trả `bo_cuc` (bài cũ / client
// lệch phiên bản). Nguồn thật là app/lessons/bo_cuc.py, đừng sửa lệch hai bên.
const PHAN_CHUAN = [
  { id: "khoi_dong", ten: "Khởi động", em: "🚀", cot: "khoi_dong" },
  { id: "hoat_dong", ten: "Hoạt động", em: "🧩", cot: "hoat_dong" },
  { id: "kien_thuc", ten: "Kiến thức trọng tâm", em: "💡", cot: "khai_niem" },
  { id: "minh_hoa", ten: "Minh hoạ", em: "🎬", cot: null },
  { id: "vi_du", ten: "Ví dụ", em: "✏️", cot: null },
  { id: "luyen_tap", ten: "Luyện tập – Vận dụng", em: "🎯", cot: "luyen_tap" },
  { id: "bai_tap", ten: "Bài tập", em: "📚", cot: "bai_tap" },
];

const SUGGESTS = [
  "Giải thích lại phần khái niệm dễ hiểu hơn",
  "Cho mình thêm một ví dụ",
  "Phần này học sinh hay nhầm chỗ nào?",
];

/** Câu hỏi mở đầu khi bấm "Hỏi về đoạn này" — tự nhiên hơn là mở thẻ trống rồi
 *  bắt học sinh nghĩ ra câu hỏi. */
const CAU_MO: Record<string, string> = {
  kien_thuc: "Giải thích lại phần kiến thức này dễ hiểu hơn giúp mình",
  khai_niem: "Giải thích lại phần khái niệm này dễ hiểu hơn giúp mình",
  minh_hoa: "Phần minh hoạ này đang nói về điều gì?",
  khoi_dong: "Phần khởi động này liên quan gì tới bài hôm nay?",
  hoat_dong: "Hướng dẫn mình làm hoạt động này với",
  luyen_tap: "Gợi ý cách làm phần luyện tập này giúp mình",
  bai_tap: "Bài tập này bắt đầu từ đâu?",
};
const cauMoViDu = (i: number) => `Ví dụ ${i + 1}: giải thích từng bước giúp mình`;

export function LessonView({ lesson, teacher, onMarkDone, onQuizGraded }: {
  lesson: Lesson; teacher: boolean; onMarkDone?: () => void;
  onQuizGraded?: (r: QuizResult) => void;
}) {
  const [showQuiz, setShowQuiz] = useState(false);
  /** Cuộn tới một phần + loé viền 2.2s (§3.4 "↑ Đọc lại phần này").
   *  Đặt ở LessonView vì chỉ nó biết phần nào đang render ở đâu. */
  const docLai = (phan: string) => {
    const el = document.getElementById(`phan-${phan}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("sang");
    window.setTimeout(() => el.classList.remove("sang"), 2200);
  };
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

  // Bố cục 7 phần. Server không trả `bo_cuc` (client cũ / bài chưa migrate) ->
  // rơi về thứ tự chuẩn, KHÔNG để trang trắng.
  const phanHien: PhanBoCuc[] = lesson.bo_cuc?.length
    ? lesson.bo_cuc
    : PHAN_CHUAN.map((x, i) => ({ ...x, an: false, so: i + 1 }));

  /** HTML của các phần lưu ở cột riêng. Phần rỗng -> không render cả tiêu đề,
   *  tránh để lại một đề mục trống trên màn hình học sinh. */
  const htmlPhan: Record<string, string | undefined> = {
    khoi_dong: lesson.khoi_dong, hoat_dong: lesson.hoat_dong,
    kien_thuc: lesson.khai_niem, luyen_tap: lesson.luyen_tap, bai_tap: lesson.bai_tap,
  };

  const DeMuc = ({ p, kt }: { p: PhanBoCuc; kt?: boolean }) => (
    <h3 className={kt ? "kt" : undefined}>
      {/* Badge "3/6" thay cho "3." — số thứ tự đơn thuần không cho biết còn mấy
          mục nữa, mà đó là thứ học sinh cuộn dài muốn biết (mockup §thân bài). */}
      <span className="hi">{p.em}</span> {p.ten}
      <span className="so-phan tnum">{p.so}/{phanHien.length}</span>
      <NutHoi neo={p.id as Neo} nhan={p.ten} hoi={CAU_MO[p.id] ?? `Giải thích phần ${p.ten.toLowerCase()} giúp mình`} />
    </h3>
  );

  const PhanNoiDung = ({ p }: { p: PhanBoCuc }) => {
    if (p.id === "minh_hoa") {
      if (!lesson.minh_hoa.length) return null;
      return (
        <>
          <DeMuc p={p} />
          <div className="media">{lesson.minh_hoa.map((m, i) => <Media key={i} m={m} />)}</div>
          {gy.minh_hoa && <div className="media-note">🎓 {gy.minh_hoa}</div>}
          <The k="minh_hoa" />
        </>
      );
    }
    if (p.id === "vi_du") {
      if (!lesson.vi_du.length) return null;
      return (
        <>
          <h3><span className="hi">{p.em}</span> {p.ten}
            <span className="so-phan tnum">{p.so}/{phanHien.length}</span></h3>
          {lesson.vi_du.map((e, i) => {
            const neo = `vi_du:${i + 1}` as Neo;
            return (
              <div key={i}>
                <div className="vd">
                  <div className="vd-top">
                    <div className="q" dangerouslySetInnerHTML={{ __html: renderMath(e.de) }} />
                    <NutHoi neo={neo} nhan={`Ví dụ ${i + 1}`} hoi={cauMoViDu(i)} ngan />
                  </div>
                  {/* Hình riêng của ví dụ: bài hình học không đọc được nếu thiếu.
                      Nằm giữa đề và lời giải, đúng thứ tự HS cần nhìn. */}
                  {e.anh && (
                    <img className="vd-hinh" src={e.anh} alt={`Hình ví dụ ${i + 1}`} loading="lazy" />
                  )}
                  <div className="a" dangerouslySetInnerHTML={{ __html: renderMath(e.giai) }} />
                </div>
                <The k={neo} />
              </div>
            );
          })}
          {gy.vi_du && <div className="media-note">🎓 {gy.vi_du}</div>}
        </>
      );
    }

    const html = htmlPhan[p.id];
    if (!html?.trim()) return null;

    // Kiến thức trọng tâm: khung cam `.kttt` + `h3.kt` (§1.3) — nhấn đây là phần
    // bắt buộc, và cũng là chỗ gắn mốc đọc + nhắc chủ động.
    if (p.id === "kien_thuc") {
      return (
        <>
          <DeMuc p={p} kt />
          <div className="kttt" ref={moc.ref} dangerouslySetInnerHTML={{ __html: renderMath(html) }} />
          <The k="kien_thuc" />
          <NhacChuDong />
        </>
      );
    }
    return (
      <>
        <DeMuc p={p} />
        {/* `.bd` để CSS bám được vào html chuyên gia soạn (bước Hoạt động, thẻ
            bài Luyện tập). Trước đây div này không có class nào nên mọi rule
            nhắm vào nội dung phần đều chết. */}
        <div className="bd" dangerouslySetInnerHTML={{ __html: renderMath(html) }} />
        <The k={p.id} />
      </>
    );
  };

  /** Nhắc chủ động ở mốc "đọc xong Kiến thức trọng tâm". Nội dung sinh sẵn lúc
   *  biên soạn nên bấm là có phản hồi ngay: KHÔNG gọi LLM, KHÔNG trừ lượt hỏi. */
  const NhacChuDong = () => {
    if (!(moc.xong && nhacKN && !tatNhac)) return null;
    return (
      <div className="nhac-boc">
        <TroLyCard topicId={lesson.topic_id} anchor="kien_thuc" nhan="Kiến thức trọng tâm" chuDong
          noiDungSan={`<p>Bạn vừa đọc xong phần kiến thức — thử nhanh một câu nhé:</p><p><b>${renderMath(nhacKN.hoi)}</b></p>`}
          nguonSan="Kiến thức trọng tâm"
          dapNhanh={nhacKN.dap.map((d, i) => ({
            t: d,
            tra: (i === nhacKN.dung
              ? "<p>🎉 Chính xác!</p>"
              : `<p>Chưa đúng rồi — đáp án đúng là <b>${renderMath((nhacKN.dap[nhacKN.dung] ?? "").replace(/\s*[.!?]+\s*$/, ""))}</b>.</p>`)
              + (nhacKN.giai ? `<p>${renderMath(nhacKN.giai)}</p>` : ""),
          }))}
          onDong={() => setTatNhac(true)} />
        <button className="nhac-tat" type="button" onClick={tatHan}>
          🔕 Đừng gợi ý kiểu này nữa
        </button>
      </div>
    );
  };

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

      {/* Render theo `bo_cuc` do SERVER tính: thứ tự + số thứ tự đều từ đó.
          Tự suy ở FE là số hiện cho học sinh lệch với bản chuyên gia đang soạn,
          và phần bị ẩn vẫn chiếm số. */}
      {phanHien.map((p) => (
        <section id={`phan-${p.id}`} className={`phan phan-${p.id}`} key={p.id}>
          <PhanNoiDung p={p} /></section>
      ))}

      {/* Hướng dẫn giảng dạy (GV) */}
      {teacher && lesson.day && (lesson.day.muc_tieu || lesson.day.thoi_luong || lesson.day.luu_y) && (
        <div className="callout">
          <b>🎓 Hướng dẫn giảng dạy.</b>{" "}
          {lesson.day.muc_tieu && <> <b>Mục tiêu:</b> {lesson.day.muc_tieu} </>}
          {lesson.day.thoi_luong && <> · <b>Thời lượng:</b> {lesson.day.thoi_luong} </>}
          {lesson.day.luu_y && <> · <b>Lưu ý:</b> {lesson.day.luu_y}</>}
        </div>
      )}

      {/* Hỏi chung cả bài — neo null, backend ghép khái niệm + ví dụ (không quiz).
          Đặt TRƯỚC bài kiểm tra: gỡ rối xong mới thi. Trước đây chip gợi ý nằm
          dưới bài kiểm tra, hoá ra hỏi "chưa rõ chỗ nào?" sau khi các em đã nộp. */}
      <div className="suggest">
        <div className="s-label">✨ Chưa rõ chỗ nào trong bài <b>{lesson.dv}</b>?</div>
        {/* Hộp chat LUÔN MỞ, gợi ý nằm bên trong. Trước đây chỉ có 3 chip: bấm
            chip mới hiện hộp, nên em nào muốn hỏi câu của riêng mình thì không
            thấy chỗ gõ. Cố ý KHÔNG truyền `hoiDau` — mở bài là gửi câu hỏi luôn
            thì mỗi lần vào bài mất một lượt hỏi trong ngày. */}
        <TroLyCard topicId={lesson.topic_id} anchor={null} nhan="Bài này"
          goiY={SUGGESTS} khongDong moiNhap="Hỏi trợ lý về bài này…"
          onDong={() => { /* hộp luôn mở */ }} />
      </div>

      <div className="divider" />

      {/* ④ Kiểm tra nhanh — CHỐT CUỐI của bài, nằm dưới cùng */}
      {lesson.co_quiz && lesson.quiz.length > 0 ? (
        showQuiz ? (
          <>
            <h3><span className="hi">✅</span> Bài kiểm tra nhanh</h3>
            <QuizView topicId={lesson.topic_id} quiz={lesson.quiz} onGraded={onQuizGraded}
              phanHien={phanHien} onDocLai={docLai} onHoiPhan={(id, ten) =>
                moThe(id, { neo: id as Neo, nhan: ten, hoi: CAU_MO[id] ?? `Giải thích phần ${ten.toLowerCase()} giúp mình` })} />
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
