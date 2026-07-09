import katex from "katex";
import type { ReactNode } from "react";

// Render nội dung có công thức $...$ bằng KaTeX; phần chữ thường giữ nguyên
// (React tự escape nên an toàn XSS). Xuống dòng "\n" -> <br/>. Chỉ hỗ trợ
// inline math $...$ — đủ cho nội dung Toán 6 backend trả về.
export function renderMath(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const parts = text.split(/(\$[^$]+\$)/g);

  parts.forEach((part, i) => {
    if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
      const tex = part.slice(1, -1);
      try {
        const html = katex.renderToString(tex, { throwOnError: false });
        nodes.push(<span key={i} dangerouslySetInnerHTML={{ __html: html }} />);
        return;
      } catch {
        /* rơi xuống render như text thường */
      }
    }
    // text thường: tách theo xuống dòng, chèn <br/>, render **đậm** -> <strong>
    const lines = part.split("\n");
    lines.forEach((line, j) => {
      if (j > 0) nodes.push(<br key={`${i}-br-${j}`} />);
      line.split(/(\*\*[^*]+\*\*)/g).forEach((seg, k) => {
        if (!seg) return;
        if (seg.startsWith("**") && seg.endsWith("**") && seg.length > 4) {
          nodes.push(<strong key={`${i}-b-${j}-${k}`}>{seg.slice(2, -2)}</strong>);
        } else {
          nodes.push(<span key={`${i}-t-${j}-${k}`}>{seg}</span>);
        }
      });
    });
  });

  return nodes;
}
