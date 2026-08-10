import { useEffect, useRef, useState } from "react";

const THOI_GIAN = 900;   // đếm tăng dần
const NHAY = 1400;       // giữ lớp sáng đủ lâu để mắt kịp bắt

/** Số liệu "biết mình vừa đổi": đếm tăng dần tới giá trị mới + báo mức chênh.
 *
 *  Trả `{hien, nhay, delta}`:
 *   - `hien`  : giá trị đang vẽ (chạy dần từ cũ sang mới)
 *   - `nhay`  : true trong ~1.4s sau khi đổi -> phía gọi gắn class để làm sáng
 *   - `delta` : chênh lệch so với lần trước (>0 thì hiện "+15")
 *
 *  LẦN ĐẦU không nhảy: vừa tải trang mà mọi ô cùng loé lên thì thành nhiễu, và
 *  người dùng tưởng vừa có gì thay đổi trong khi chỉ là số cũ.
 */
export function useSoDoi(gia_tri: number) {
  const [hien, setHien] = useState(gia_tri);
  const [nhay, setNhay] = useState(false);
  const [delta, setDelta] = useState(0);
  const truoc = useRef<number | null>(null);

  useEffect(() => {
    const cu = truoc.current;
    truoc.current = gia_tri;

    if (cu === null || cu === gia_tri) { setHien(gia_tri); return; }

    setDelta(gia_tri - cu);
    setNhay(true);
    const tNhay = window.setTimeout(() => { setNhay(false); setDelta(0); }, NHAY);

    // Đếm bằng requestAnimationFrame + easing: nhảy phắt sang số mới thì mắt
    // không kịp nhận ra là nó đã đổi.
    let raf = 0;
    const bat_dau = performance.now();
    const chay = (t: number) => {
      const k = Math.min(1, (t - bat_dau) / THOI_GIAN);
      const e = 1 - Math.pow(1 - k, 3);   // ease-out cubic
      setHien(Math.round(cu + (gia_tri - cu) * e));
      if (k < 1) raf = requestAnimationFrame(chay);
    };
    raf = requestAnimationFrame(chay);

    return () => { window.clearTimeout(tNhay); cancelAnimationFrame(raf); };
  }, [gia_tri]);

  return { hien, nhay, delta };
}
