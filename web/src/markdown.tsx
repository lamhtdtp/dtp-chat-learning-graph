import katex from "katex";
import type { ReactNode } from "react";
import type { Citation } from "./types";

type CiteMap = Map<number, Citation>;
type OnCite = (c: Citation) => void;

// Render 1 công thức LaTeX qua KaTeX. display=true cho $$...$$ (căn giữa).
function renderMath(latex: string, key: string, display: boolean): ReactNode {
  try {
    const html = katex.renderToString(latex, { throwOnError: false, displayMode: display });
    return <span key={key} dangerouslySetInnerHTML={{ __html: html }} />;
  } catch {
    return <span key={key}>{latex}</span>; // cú pháp lỗi -> text thô, không vỡ UI
  }
}

// Render inline: $$công thức$$, $công thức$, **đậm** (đệ quy: đậm VẪN render công
// thức/trích dẫn bên trong), và [tr.N] -> chip trích dẫn bấm được.
function renderInline(text: string, keyBase: string, cites: CiteMap, onCite: OnCite): ReactNode[] {
  // $$...$$ đặt TRƯỚC $...$ để khớp công thức căn giữa; **...** khớp trước để đệ quy.
  const parts = text.split(/(\$\$[^$]+\$\$|\$[^$]+\$|\*\*[^*]+\*\*|\[tr\.\d+\])/g);
  const nodes: ReactNode[] = [];
  parts.forEach((part, i) => {
    const key = `${keyBase}-${i}`;
    if (!part) return;

    if (part.startsWith("$$") && part.endsWith("$$") && part.length > 4) {
      nodes.push(renderMath(part.slice(2, -2), key, true));
      return;
    }
    if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
      nodes.push(renderMath(part.slice(1, -1), key, false));
      return;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      // Đệ quy: công thức/trích dẫn trong nhãn đậm cũng được render (trước đây
      // hiện literal "$\mathbb{Z}$" vì lấy text thô).
      nodes.push(<strong key={key}>{renderInline(part.slice(2, -2), key, cites, onCite)}</strong>);
      return;
    }
    const citeMatch = part.match(/^\[tr\.(\d+)\]$/);
    if (citeMatch) {
      const page = Number(citeMatch[1]);
      const c = cites.get(page);
      if (c) {
        const bai = c.bai_so != null ? ` · Bài ${c.bai_so}` : "";
        nodes.push(
          <button key={key} className="cite-inline" onClick={() => onCite(c)} type="button" title={`Xem trang ${page}`}>
            <span className="cite-ico">📖</span>Trang {page}{bai}
          </button>,
        );
      } else {
        nodes.push(
          <span key={key} className="cite-inline muted">
            <span className="cite-ico">📖</span>Trang {page}
          </span>,
        );
      }
      return;
    }
    nodes.push(<span key={key}>{part}</span>);
  });
  return nodes;
}

// Render markdown rút gọn: heading (#..######), gạch đầu dòng (*/-), đoạn văn;
// inline có đậm/công thức/chip trang. Đủ cho câu trả lời của trợ lý.
export function renderRich(text: string, cites: CiteMap, onCite: OnCite): ReactNode[] {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let list: ReactNode[] = [];
  let key = 0;

  const flushList = () => {
    if (list.length) {
      blocks.push(<ul key={`ul-${key++}`}>{list}</ul>);
      list = [];
    }
  };

  lines.forEach((raw) => {
    const line = raw.trimEnd();
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    const bullet = line.match(/^\s*[*-]\s+(.*)$/);

    if (heading) {
      flushList();
      const level = Math.min(heading[1].length, 4);
      const Tag = (["h3", "h3", "h4", "h4"][level - 1] ?? "h4") as "h3" | "h4";
      blocks.push(<Tag key={`h-${key++}`} className="md-h">{renderInline(heading[2], `h${key}`, cites, onCite)}</Tag>);
    } else if (bullet) {
      list.push(<li key={`li-${key++}`}>{renderInline(bullet[1], `li${key}`, cites, onCite)}</li>);
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      blocks.push(<p key={`p-${key++}`} className="md-p">{renderInline(line, `p${key}`, cites, onCite)}</p>);
    }
  });
  flushList();
  return blocks;
}
