import { useEffect, useRef } from "react";
import { pingPhien } from "../api";

const NHIP = 30_000;   // 30s/lần — khớp trần server (_TRAN_PING=120s, dư sức trễ)

/** Ghi thời gian học: ping mỗi 30s CHỈ KHI tab đang hiện.
 *
 *  Đếm cả lúc tab ẩn thì "thời gian học" thành thời gian mở tab rồi đi chơi — số
 *  đó vô nghĩa với cả học sinh lẫn giáo viên. Server cộng dồn và chặn trần, client
 *  chỉ nói "vừa học thêm 30 giây".
 */
export function usePingPhien(topicId: number | null, phanDoc: string[] = []) {
  const idRef = useRef<number | undefined>(undefined);
  // Đọc qua ref: interval gắn 1 lần nhưng luôn gửi danh sách MỚI NHẤT. Nếu đưa
  // phanDoc vào deps thì mỗi lần đọc thêm một phần là interval bị dựng lại và
  // nhịp 30s không bao giờ tới.
  const phanRef = useRef(phanDoc);
  phanRef.current = phanDoc;

  useEffect(() => {
    if (topicId == null) return;
    const chay = () => {
      if (document.visibilityState === "visible") {
        pingPhien(topicId, NHIP / 1000, phanRef.current)
          .catch(() => { /* mất mạng: bỏ nhịp này */ });
      }
    };
    idRef.current = window.setInterval(chay, NHIP);
    return () => window.clearInterval(idRef.current);
  }, [topicId]);
}
