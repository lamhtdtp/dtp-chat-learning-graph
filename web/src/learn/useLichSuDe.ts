import { useCallback, useEffect, useState } from "react";
import { ApiError, dsDeCuoiKy, xoaDeCuoiKy, xoaHetDeCuoiKy } from "../api";
import type { DeCuoiKyTomTat } from "../types";

/** Lịch sử đề cuối kỳ: tải từng trang, "Xem thêm", xoá một đề / xoá tất cả.
 *  Dùng chung cho màn đề cuối kỳ (lọc theo kỳ) và Hồ sơ học tập (mọi kỳ) — hai
 *  nơi hiện cùng một danh sách thì phải cùng một cách tải và xoá. */
export function useLichSuDe(exam: string | undefined, gioiHan: number, bat = true) {
  const [ds, setDs] = useState<DeCuoiKyTomTat[] | null>(null);
  const [conNua, setConNua] = useState(false);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  const tai = useCallback(() => {
    setLoi(null);
    dsDeCuoiKy(exam, { gioiHan })
      .then((r) => { setDs(r.de); setConNua(r.con_nua); })
      .catch(() => { setDs([]); setConNua(false); });
  }, [exam, gioiHan]);

  useEffect(() => { if (bat) tai(); }, [bat, tai]);

  const xemThem = async () => {
    if (!ds) return;
    setDangTai(true);
    try {
      const r = await dsDeCuoiKy(exam, { gioiHan, boQua: ds.length });
      // Khử trùng theo de_id: giữa hai lần tải mà có đề mới, trang sau lệch đi
      // một dòng và lặp lại đề cuối của trang trước.
      setDs((cu) => {
        const co = new Set((cu ?? []).map((x) => x.de_id));
        return [...(cu ?? []), ...r.de.filter((x) => !co.has(x.de_id))];
      });
      setConNua(r.con_nua);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không tải thêm được, thử lại nhé");
    } finally { setDangTai(false); }
  };

  /** Trả true nếu đã xoá (người dùng xác nhận và server đồng ý). */
  const xoa = async (x: DeCuoiKyTomTat): Promise<boolean> => {
    const ten = x.da_nop ? `đề làm lúc ${new Date(x.nop_luc ?? x.luc).toLocaleString("vi-VN")}`
      : "đề chưa nộp này";
    if (!window.confirm(`Xoá hẳn ${ten}?\n\nKết quả, đáp án đã chọn và thống kê của đề này sẽ mất, `
      + "thầy cô cũng không còn thấy. Không khôi phục được.")) return false;
    setLoi(null);
    try {
      await xoaDeCuoiKy(x.de_id);
      try { localStorage.removeItem(`ck-nhap:${x.de_id}`); } catch { /* bỏ qua */ }
      setDs((cu) => (cu ?? []).filter((y) => y.de_id !== x.de_id));
      return true;
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được, thử lại nhé");
      return false;
    }
  };

  const xoaHet = async (): Promise<boolean> => {
    const pham_vi = exam ? `mọi đề cuối kỳ ${exam.replace(/\D/g, "")}` : "toàn bộ lịch sử đề cuối kỳ";
    if (!window.confirm(`Xoá hẳn ${pham_vi}?\n\nMọi kết quả và thống kê của các đề này sẽ mất, `
      + "thầy cô cũng không còn thấy. Không khôi phục được.")) return false;
    setLoi(null);
    try {
      await xoaHetDeCuoiKy(exam);
      try {
        for (const x of ds ?? []) localStorage.removeItem(`ck-nhap:${x.de_id}`);
      } catch { /* bỏ qua */ }
      setDs([]); setConNua(false);
      return true;
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không xoá được, thử lại nhé");
      return false;
    }
  };

  return { ds, conNua, dangTai, loi, tai, xemThem, xoa, xoaHet };
}
