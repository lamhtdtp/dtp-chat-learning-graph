import { useEffect, useRef, useState } from "react";

// Nhịp đo. 500ms đủ mịn cho một mốc tính bằng giây, và mỗi nhịp chỉ là một lần
// đọc getBoundingClientRect của đúng một phần tử.
const NHIP_MS = 500;

// "Đã đọc qua" = đáy khối đã lên trên mốc này (tính theo chiều cao màn hình).
// KHÔNG dùng 0 (tức là trôi hẳn khỏi màn hình): màn hình cao mà bài ngắn thì
// cuộn tới đáy trang rồi đáy khối vẫn còn nằm trong tầm nhìn, mốc sẽ KHÔNG BAO
// GIỜ bật — im lặng, không lỗi, rất khó lần ra.
const NGUONG_DAY = 0.35;

/** Bật một lần khi học sinh ĐỌC XONG một khối trong bài.
 *
 *  "Đọc xong" = khối đã nằm trong tầm nhìn ít nhất `giay` giây, RỒI trôi hẳn lên
 *  trên khỏi màn hình. Hai vế đều cần:
 *  - chỉ "đã nhìn thấy" thì cuộn vèo qua cũng tính, nhắc lúc em ấy chưa đọc gì;
 *  - chỉ "trôi khỏi màn hình" thì nhảy thẳng xuống cuối bài cũng bị nhắc.
 *
 *  CỐ Ý dùng vòng đo theo nhịp chứ KHÔNG dùng IntersectionObserver: Chrome treo
 *  việc phát callback của IO khi `document.visibilityState === "hidden"` (tab
 *  nền, cửa sổ không focus, và mọi trình duyệt tự động hoá) — mốc sẽ im lặng
 *  không bao giờ bật mà không có lỗi nào để lần. Đọc rect theo nhịp thì đo được
 *  ở mọi nơi và kiểm chứng được. Vòng đo tự dừng ngay khi mốc bật.
 *
 *  Bắn ĐÚNG MỘT LẦN mỗi phiên xem bài (đổi bài -> component unmount -> reset).
 */
export function useMocDoc(bat: boolean, giay = 4) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [xong, setXong] = useState(false);
  const hienMs = useRef(0);

  useEffect(() => {
    if (!bat || xong) return;
    hienMs.current = 0;

    const id = setInterval(() => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const cao = window.innerHeight || document.documentElement.clientHeight;

      if (r.bottom > 0 && r.top < cao) hienMs.current += NHIP_MS;

      // Đáy khối đã lên quá ngưỡng => học sinh đang đọc phần SAU nó. Khối còn
      // nằm dưới màn hình (r.bottom >= cao) thì chưa đọc tới, không tính.
      if (r.bottom < cao * NGUONG_DAY && hienMs.current >= giay * 1000) {
        clearInterval(id);
        setXong(true);
      }
    }, NHIP_MS);

    return () => clearInterval(id);
  }, [bat, xong, giay]);

  return { ref, xong };
}
