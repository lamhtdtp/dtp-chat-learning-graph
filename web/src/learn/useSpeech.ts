import { useCallback, useEffect, useRef, useState } from "react";

/** Web Speech API chưa có trong lib.dom của TypeScript (vẫn là draft, Chrome/Safari
 *  cài dưới tiền tố webkit) -> khai báo phần tối thiểu đang dùng, không kéo thêm
 *  package @types nào. */
interface SpeechResult { readonly isFinal: boolean; readonly length: number; [i: number]: { transcript: string } }
interface SpeechEvent { readonly resultIndex: number; readonly results: { readonly length: number; [i: number]: SpeechResult } }
interface SpeechErrorEvent { readonly error: string }
interface Recognition {
  lang: string; continuous: boolean; interimResults: boolean;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: SpeechEvent) => void) | null;
  onerror: ((e: SpeechErrorEvent) => void) | null;
  onend: (() => void) | null;
}
type RecognitionCtor = new () => Recognition;

function ctor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// Thông báo theo mã lỗi chuẩn của Web Speech API. Nói rõ cách xử lý, vì đa số
// trường hợp là học sinh bấm "Chặn" ở hộp xin quyền micro.
const _LOI: Record<string, string> = {
  "not-allowed": "Trình duyệt chưa cho phép dùng micro. Bấm vào biểu tượng khoá 🔒 trên thanh địa chỉ để bật lại.",
  "service-not-allowed": "Trình duyệt chưa cho phép dùng micro.",
  "no-speech": "Mình chưa nghe thấy gì. Bạn thử nói lại nhé.",
  "audio-capture": "Không tìm thấy micro nào trên máy.",
  network: "Mất kết nối khi nhận dạng giọng nói.",
};

/** Nhập câu hỏi bằng giọng nói (tiếng Việt).
 *
 *  `onFinal` nhận đoạn đã nhận dạng xong để ghép vào ô nhập; `interim` là phần
 *  đang nghe dở, hiện tạm cho học sinh thấy máy đang bắt được chữ.
 *
 *  Không hỗ trợ (Firefox, một số webview) -> `supported=false`, phía gọi ẩn hẳn
 *  nút micro thay vì hiện một nút bấm vào không có gì xảy ra.
 */
export function useSpeech(onFinal: (text: string) => void, lang = "vi-VN") {
  const [supported] = useState(() => ctor() !== null);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  // onFinal qua ref: handler chỉ gắn 1 lần, nhưng luôn gọi bản mới nhất (nếu
  // đóng gói trực tiếp thì nó bắt mất `input` của lần render đầu).
  const finalRef = useRef(onFinal);
  finalRef.current = onFinal;

  const stop = useCallback(() => recRef.current?.stop(), []);

  const start = useCallback(() => {
    const C = ctor();
    if (!C) return;
    // Bỏ phiên cũ trước: gọi start() khi bản ghi trước chưa kịp `onend` sẽ ném
    // InvalidStateError (bấm micro hai lần thật nhanh).
    recRef.current?.abort();
    setLoi(null);
    const rec = new C();
    rec.lang = lang;
    rec.continuous = false;   // tự dừng khi học sinh ngừng nói — 1 lần bấm = 1 câu hỏi
    rec.interimResults = true;
    rec.onresult = (e) => {
      let xong = "", dang = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        (r.isFinal ? (xong += r[0].transcript) : (dang += r[0].transcript));
      }
      if (xong) finalRef.current(xong);
      setInterim(dang);
    };
    rec.onerror = (e) => {
      // "aborted" xảy ra khi chính ta gọi abort() lúc rời trang — không phải lỗi.
      if (e.error !== "aborted") setLoi(_LOI[e.error] ?? "Không dùng được micro lúc này.");
    };
    rec.onend = () => { setListening(false); setInterim(""); };
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [lang]);

  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);

  // Rời trang giữa chừng mà không abort thì micro vẫn sáng đèn.
  useEffect(() => () => recRef.current?.abort(), []);

  return { supported, listening, interim, loi, start, stop, toggle };
}
