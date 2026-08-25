import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, askTutor, getTutorLimits, tokenStore } from "../api";
import { renderMath } from "../mathHtml";
import type { AnhKem, Neo } from "../types";
import { useSpeech } from "./useSpeech";

type Luot = { hoi: string; dap: string; nguonBai: string | null; loi?: boolean;
              anh?: AnhKem[] };

// Dùng khi GET /tutor/limits lỗi. Giữ khớp mặc định settings.chat_max_chars.
const FALLBACK_MAX_CHARS = 500;

/** Chuẩn hoá câu trả lời -> HTML. Giống ChatPanel: renderMath lo LaTeX và bỏ
 *  trích trang [tr.45]; ở đây chỉ thêm markdown nhẹ. */
function toHtml(answer: string): string {
  return renderMath(answer)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/(^|\n)\s*[*•-]\s+/g, "$1• ")
    .replace(/\s+([.,;!?])/g, "$1")
    .replace(/\n{2,}/g, "<br><br>")
    .replace(/\n/g, "<br>");
}

/** Trợ lý trả lời NGAY TRONG BÀI, neo vào đúng đoạn học sinh đang đọc.
 *
 *  Một component, hai nguồn phát:
 *  - học sinh bấm hỏi ở một mục  -> `hoiDau` là câu hỏi mở đầu;
 *  - hệ thống tự lên tiếng ở mốc -> `chuDong` + `noiDungSan` (không gọi API,
 *    không tốn lượt hỏi).
 */
export function TroLyCard({
  topicId, anchor, nhan, hoiDau, chuDong, noiDungSan, nguonSan, dapNhanh, an, onDong,
  goiY, khongDong, moiNhap,
}: {
  topicId: number;
  /** null = hỏi chung cả bài (backend ghép khái niệm + ví dụ, không kèm quiz). */
  anchor: Neo | null;
  /** Nhãn hiển thị của đoạn, vd "Ví dụ 2". */
  nhan: string;
  /** Câu hỏi bắn ngay khi thẻ mở. Bỏ trống nếu dùng `noiDungSan`. */
  hoiDau?: string;
  /** Thẻ do trợ lý tự mở (đổi màu + gắn nhãn "Trợ lý chủ động"). */
  chuDong?: boolean;
  /** Nội dung dựng sẵn ở client (vd lời giải câu sai) — KHÔNG gọi LLM. */
  noiDungSan?: string;
  nguonSan?: string;
  /** Nút trả lời nhanh dưới lượt đầu (trợ lý chủ động hỏi lại).
   *  Có `tra` -> phản hồi dựng sẵn, trả lời NGAY tại client (0 lượt hỏi).
   *  Không có `tra` -> gửi lên trợ lý như câu hỏi bình thường (tính 1 lượt). */
  dapNhanh?: { t: string; tra?: string }[];
  /** Ẩn bằng CSS chứ KHÔNG unmount: đóng rồi mở lại từ "Đã hỏi" phải còn nguyên
   *  hội thoại, chứ hỏi lại là mất thêm một lượt của học sinh. */
  an?: boolean;
  onDong: () => void;
  /** Câu gợi ý hiện NGAY TRONG hộp chat, chỉ khi chưa có lượt nào — bấm là gửi.
   *  Trước đây chip gợi ý nằm ngoài, phải bấm mới hiện hộp chat; học sinh muốn
   *  tự gõ câu khác thì không thấy chỗ nào để gõ. */
  goiY?: string[];
  /** Hộp luôn mở (hỏi chung cả bài) -> không có gì để đóng, ẩn nút ✕. */
  khongDong?: boolean;
  /** Ghi đè placeholder. Hộp luôn mở thì "Hỏi tiếp…" là sai — chưa hỏi gì cả. */
  moiNhap?: string;
}) {
  const [luots, setLuots] = useState<Luot[]>(
    noiDungSan ? [{ hoi: "", dap: noiDungSan, nguonBai: nguonSan ?? nhan }] : [],
  );
  const [dangCho, setDangCho] = useState(false);
  const [input, setInput] = useState("");
  // Bắn câu mở đầu ĐÚNG MỘT LẦN: StrictMode gọi effect hai lượt, không chốt lại
  // thì mỗi lần mở thẻ là hai request và trừ hai lượt hỏi của học sinh.
  const daBan = useRef(false);
  // Chặn độ dài ở client cho mọi đường vào: để 400 của server là nơi đầu tiên
  // học sinh biết mình viết quá dài thì đã mất một vòng request.
  const [maxChars, setMaxChars] = useState(FALLBACK_MAX_CHARS);
  useEffect(() => {
    getTutorLimits().then((l) => setMaxChars(l.max_chars)).catch(() => { /* giữ fallback */ });
  }, []);
  const themLoiNoi = useCallback((t: string) => {
    setInput((cu) => (cu && !cu.endsWith(" ") ? cu + " " + t : cu + t).slice(0, maxChars));
  }, [maxChars]);
  const mic = useSpeech(themLoiNoi);

  const hoi = async (cau: string) => {
    const q = cau.trim();
    if (!q || dangCho) return;
    if (mic.listening) mic.stop();   // gửi rồi thì tắt micro, không nghe tiếp vào câu đã gửi
    setInput("");
    setDangCho(true);
    try {
      const a = await askTutor(q, "Toán", { topicId, anchor });
      // `a.citations` (số trang SGK) CỐ Ý không hiển thị: học sinh không tra
      // sách giấy khi đang học trên máy, mà mỗi câu trả lời lại đính 2-3 nhãn
      // trang thành ra nhiễu. Nhãn "Bài đang học" mới là thứ các em cần biết.
      setLuots((l) => [...l, { hoi: q, dap: toHtml(a.answer), nguonBai: a.nguon_bai,
                               anh: a.anh }]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); location.reload(); return; }
      const msg = e instanceof ApiError ? e.message : "Không kết nối được máy chủ";
      setLuots((l) => [...l, { hoi: q, dap: "⚠️ " + msg, nguonBai: null, loi: true }]);
    } finally {
      setDangCho(false);
    }
  };

  useEffect(() => {
    if (hoiDau && !daBan.current) { daBan.current = true; hoi(hoiDau); }
  }, [hoiDau]); // eslint-disable-line react-hooks/exhaustive-deps

  // Lượt đầu do trợ lý tự mở mà học sinh chưa đáp -> còn hiện nút trả lời nhanh.
  const conDapNhanh = !!dapNhanh?.length && luots.length === 1 && !dangCho;

  return (
    <div className={"tl-card" + (chuDong ? " chu-dong" : "") + (an ? " an" : "")}
      aria-hidden={an || undefined}>
      <div className="tl-head">
        <span className="tl-ava" aria-hidden>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>
        </span>
        <b>{chuDong ? "Trợ lý gợi ý" : "Trợ lý"}</b>
        <span className="tl-neo">📍 {nhan}</span>
        {!khongDong && (
          <button className="tl-x" type="button" onClick={onDong} aria-label="Đóng phần trả lời">✕</button>
        )}
      </div>

      <div className="tl-body">
        {luots.map((l, i) => (
          <div className="tl-luot" key={i}>
            {l.hoi && <div className="tl-hoi">{l.hoi}</div>}
            <div className={"tl-dap" + (l.loi ? " loi" : "")} dangerouslySetInnerHTML={{ __html: l.dap }} />
            {/* Hình LẤY TỪ BÀI ĐANG HỌC, không sinh mới: câu trả lời về hình học
                mà chỉ có chữ thì em phải cuộn lên bài để nhìn lại. */}
            {!!l.anh?.length && (
              <div className="tl-anh">
                {l.anh.map((a) => (
                  <figure key={a.url}>
                    <img src={a.url} alt={a.caption} loading="lazy" />
                    <figcaption><b>{a.tu}</b> {a.caption}</figcaption>
                  </figure>
                ))}
              </div>
            )}
            {!l.loi && l.nguonBai && (
              <div className="tl-nguon">
                <span className="ng bai">📖 Bài đang học · {l.nguonBai}</span>
              </div>
            )}
          </div>
        ))}
        {/* Gợi ý nằm TRONG hộp, mất đi sau lượt đầu: giữ lại thì chiếm chỗ của
            hội thoại, mà lúc đó học sinh đã biết gõ vào đâu rồi. */}
        {!!goiY?.length && luots.length === 0 && !dangCho && (
          <div className="tl-goiy">
            {goiY.map((q) => (
              <button type="button" key={q} onClick={() => hoi(q)}>💬 {q}</button>
            ))}
          </div>
        )}
        {dangCho && <div className="typing" aria-label="Trợ lý đang trả lời"><i /><i /><i /></div>}
        {conDapNhanh && (
          <div className="tl-nhanh">
            {dapNhanh!.map((d) => (
              <button type="button" key={d.t} onClick={() => (d.tra
                ? setLuots((l) => [...l, { hoi: d.t, dap: d.tra!, nguonBai: nhan }])
                : hoi(d.t))}>{d.t}</button>
            ))}
          </div>
        )}
      </div>

      {mic.listening && (
        <div className="tl-mic-live" aria-live="polite">
          <span className="mic-wave" aria-hidden><i /><i /><i /></span>
          {mic.interim || "Đang nghe… bạn nói câu hỏi đi"}
        </div>
      )}
      {mic.loi && <div className="tl-mic-loi">⚠️ {mic.loi}</div>}

      <div className="tl-in">
        <input value={input}
          placeholder={moiNhap ?? `Hỏi tiếp về ${nhan.toLowerCase()}…`} disabled={dangCho}
          maxLength={maxChars} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); hoi(input); } }} />
        {/* Trình duyệt không có Web Speech API (Firefox…) -> ẩn hẳn nút micro */}
        {mic.supported && (
          <button type="button" className={"tl-mic" + (mic.listening ? " on" : "")} disabled={dangCho}
            onClick={mic.toggle} aria-pressed={mic.listening}
            aria-label={mic.listening ? "Dừng ghi âm" : "Nhập bằng giọng nói"}>
            {mic.listening
              ? <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
              : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1"><rect x="9" y="2" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v4" /></svg>}
          </button>
        )}
        <button type="button" className="tl-gui" disabled={dangCho || !input.trim()}
          onClick={() => hoi(input)} aria-label="Gửi">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
        </button>
      </div>
    </div>
  );
}
