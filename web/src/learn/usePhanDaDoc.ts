import { useEffect, useRef, useState } from "react";

const NHIP = 900;        // ms — cùng cách làm với useMocDoc (polling rect)
const NGUONG = 0.6;      // đáy phần đã lên trên 60% khung nhìn = coi như đã đọc

/** Các phần học sinh đã CUỘN QUA, đo bằng `getBoundingClientRect` theo nhịp.
 *
 *  Cố ý KHÔNG dùng IntersectionObserver (REQ §0): nó không bắn trong browser tự
 *  động hoá nên không test/chụp được — cùng lý do với `useMocDoc`.
 *
 *  Chỉ THÊM vào, không bớt: cuộn lên trên không phải là "chưa đọc nữa".
 */
export function usePhanDaDoc(phanIds: string[], bat: boolean) {
  const [daDoc, setDaDoc] = useState<string[]>([]);
  const ref = useRef<Set<string>>(new Set());

  // Đổi bài -> dọn: phần đã đọc thuộc về bài cũ.
  const khoa = phanIds.join(",");
  useEffect(() => { ref.current = new Set(); setDaDoc([]); }, [khoa]);

  useEffect(() => {
    if (!bat || !phanIds.length) return;
    const id = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      let doi = false;
      for (const p of phanIds) {
        if (ref.current.has(p)) continue;
        const r = document.getElementById(`phan-${p}`)?.getBoundingClientRect();
        if (r && r.bottom <= window.innerHeight * NGUONG) {
          ref.current.add(p);
          doi = true;
        }
      }
      if (doi) setDaDoc([...ref.current]);
    }, NHIP);
    return () => window.clearInterval(id);
  }, [khoa, bat]);

  return daDoc;
}
