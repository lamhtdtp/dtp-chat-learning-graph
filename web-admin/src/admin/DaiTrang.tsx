import type { BookJob, SoatSach } from "../types";

export type OTrang = "xong" | "dang" | "loi" | "thieu" | "cho";

/** Dải ô trang: MỘT ô cho mỗi trang (REQ §2.4).
 *
 *  Vì sao không liệt kê từng dòng: một tập là 151 trang. Câu hỏi duy nhất của
 *  người soạn là “đủ và đúng thứ tự chưa?” — nhìn dải ô thấy ngay chỗ hổng,
 *  còn 151 dòng thì không ai đọc. Nạp sai thứ tự trang là mọi dẫn nguồn
 *  “[tr.9]” trỏ sai bài, mà chỉ học sinh mới phát hiện. */
export function DaiTrang({ o, chuGiai }: {
  o: { so: number; tt: OTrang }[];
  chuGiai: { tt: OTrang; nhan: string }[];
}) {
  if (!o.length) return null;
  return (
    <>
      <div className="dai">
        {o.map(({ so, tt }) => (
          <span key={so} className={"o o-" + tt} title={`Trang ${so}`} />
        ))}
      </div>
      <div className="dai-cg">
        {chuGiai.filter((c) => o.some((x) => x.tt === c.tt)).map((c) => (
          <span key={c.tt}><i className={"o o-" + c.tt} />{c.nhan}</span>
        ))}
      </div>
    </>
  );
}

/** Dải ô cho màn CHỌN TỆP: xanh = có ảnh, viền đỏ = khuyết ở giữa. */
export function daiTuSoat(d: SoatSach): { so: number; tt: OTrang }[] {
  if (!d.trang.length) return [];
  const co = new Set(d.trang);
  const het = Math.max(...d.trang);
  const dau = Math.min(...d.trang);
  const ra: { so: number; tt: OTrang }[] = [];
  for (let n = dau; n <= het; n++) ra.push({ so: n, tt: co.has(n) ? "xong" : "thieu" });
  return ra;
}

/** Dải ô cho màn ĐANG NẠP: xong / đang đọc / lỗi / chưa tới. */
export function daiTuJob(j: BookJob): { so: number; tt: OTrang }[] {
  const xong = new Set(j.trang_xong);
  const loi = new Set(j.trang_loi.map((x) => x.so));
  return j.trang.map((so) => ({
    so,
    tt: loi.has(so) ? "loi" : so === j.trang_dang ? "dang" : xong.has(so) ? "xong" : "cho",
  }));
}
