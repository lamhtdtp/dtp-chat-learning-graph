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

// Trích trang sách "[tr.45]" mà AI chèn vào để chứng minh bám SGK. Có ích lúc
// biên soạn, nhưng KHÔNG hiện cho người đọc — nguồn đã nói ở chỗ khác ("Bám SGK
// trang 45, 46"). Bỏ cả khoảng trắng đứng trước để không hở đôi dấu cách.
// Khớp cả "[Bài đang học]" / "[Bài đang học, tr.11]": prompt đã dặn đừng chèn
// nhãn cho nội dung bài, nhưng mô hình vẫn tự chế ra — chốt chặn ở đây để một
// lần lệch prompt không đổ thẳng cái nhãn xấu xí lên màn hình học sinh.
const TRICH_TRANG = /\s*\[\s*(?:tr\.?\s*\d+|bài đang học[^\]]*)\s*\]/gi;

/** Bỏ trích trang + đổi `$$…$$` (khối), `$…$`, `\(…\)` thành HTML KaTeX. */
export function renderMath(html: string): string {
  return html
    .replace(TRICH_TRANG, "")
    .replace(/\$\$([^$]+?)\$\$/g, (_, m) => tex(m, true))
    .replace(/\$([^$\n]+?)\$/g, (_, m) => tex(m, false))
    .replace(/\\\((.+?)\\\)/g, (_, m) => tex(m, false));
}
