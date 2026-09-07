import { useEffect, useState } from "react";
import { getTutorLimits } from "../api";

/** Lời nhắn bảo trì trợ lý AI, hoặc null nếu đang hoạt động.
 *
 *  Đọc từ GET /tutor/limits — hàm đó đã cache theo phiên nên gọi ở nhiều
 *  component cũng chỉ một request. Có state này thì nút "Hỏi" tắt được NGAY,
 *  học sinh không bấm vào rồi mới biết là không hỏi được. */
export function useBaoTri(): string | null {
  const [nhan, setNhan] = useState<string | null>(null);
  useEffect(() => {
    let huy = false;
    getTutorLimits()
      .then((l) => {
        if (!huy) setNhan(l.bao_tri ? (l.bao_tri_nhan || "Trợ lý AI đang bảo trì.") : null);
      })
      // Không gọi được limits thì COI NHƯ đang hoạt động: chặn oan vì mạng chớp
      // một nhịp thì học sinh mất luôn trợ lý.
      .catch(() => { /* bỏ qua */ });
    return () => { huy = true; };
  }, []);
  return nhan;
}
