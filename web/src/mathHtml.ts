/** Render công thức LaTeX nhúng trong HTML nội dung bài học.
 *
 *  Nội dung do chuyên gia/AI soạn được lưu là HTML thuần (`<p>`, `<b>`…) có
 *  chèn công thức kiểu LaTeX giữa cặp `$…$` / `$$…$$`. Module này đổi các công
 *  thức đó thành HTML của KaTeX và GIỮ NGUYÊN mọi thẻ HTML khác, để cùng một
 *  chuỗi hiện y hệt nhau ở trang học của HS và ở ô "Xem trước" trong CMS.
 *
 *  ⚠️ BẢN SAO: phải khớp với web-admin/src/mathHtml.ts. Hai app build trong 2
 *  container riêng (infra/frontend.Dockerfile chỉ COPY web/, frontend-admin
 *  chỉ COPY web-admin/) nên không dùng được file chung ở gốc repo. Sửa một bên
 *  thì sửa cả bên kia, không thì preview của CMS lệch với HS thấy.
 */
import katex from "katex";

function tex(src: string, display: boolean): string {
  try {
    return katex.renderToString(src, { displayMode: display, throwOnError: false });
  } catch {
    return src;   // công thức sai cú pháp -> để nguyên văn, không làm sập trang
  }
}

/** Đổi `$$…$$` (khối), `$…$` và `\(…\)` (inline) trong `html` thành HTML KaTeX. */
export function renderMath(html: string): string {
  return html
    .replace(/\$\$([^$]+?)\$\$/g, (_, m) => tex(m, true))
    .replace(/\$([^$\n]+?)\$/g, (_, m) => tex(m, false))
    .replace(/\\\((.+?)\\\)/g, (_, m) => tex(m, false));
}
