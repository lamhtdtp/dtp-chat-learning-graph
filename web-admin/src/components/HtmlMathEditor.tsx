import { useMemo, useState } from "react";
import { renderMath } from "../mathHtml";

/** Ô soạn nội dung HTML + công thức LaTeX — thay cho `<textarea>` trơn.
 *
 *  Vì nội dung được LƯU nguyên dạng HTML (API/DB không đổi), component giữ
 *  textarea làm nơi nhập mã nguồn và thêm tab "Xem" render bằng đúng
 *  `renderMath` mà trang học của HS dùng → tác giả thấy trước y như HS thấy,
 *  không còn phải đoán chuỗi `$\frac{a}{b}$` ra hình gì.
 *
 *  Không dùng WYSIWYG (TipTap/Quill) vì các editor đó chuẩn hoá HTML theo schema
 *  riêng, sẽ viết lại nội dung HTML cũ khi lưu và phải cấu hình thêm node cho
 *  công thức.
 */
export function HtmlMathEditor({ value, onChange, placeholder, minHeight, style, id }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  /** Chiều cao tối thiểu của vùng nhập/xem (px). */
  minHeight?: number;
  style?: React.CSSProperties;
  id?: string;
}) {
  const [tab, setTab] = useState<"src" | "pv">("src");
  // Chỉ render lại KaTeX khi nội dung/tab đổi — tránh chạy lại mỗi keystroke ở tab nhập.
  const html = useMemo(() => (tab === "pv" ? renderMath(value) : ""), [tab, value]);
  const co = minHeight ?? 96;

  return (
    <div className="hme" style={style}>
      <div className="hme-bar">
        <div className="seg seg-sm">
          <button className={tab === "src" ? "on" : ""} type="button" onClick={() => setTab("src")}>✍️ Nhập</button>
          <button className={tab === "pv" ? "on" : ""} type="button" onClick={() => setTab("pv")}>👁 Xem</button>
        </div>
        <span className="hme-hint">HTML + công thức trong $…$</span>
      </div>
      {tab === "src" ? (
        <textarea id={id} value={value} placeholder={placeholder} style={{ minHeight: co }}
          spellCheck={false} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <div className="hme-pv" style={{ minHeight: co }}
          dangerouslySetInnerHTML={{ __html: html || "<i>(chưa có nội dung)</i>" }} />
      )}
    </div>
  );
}
