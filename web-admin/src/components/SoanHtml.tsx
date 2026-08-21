import { useEffect, useRef } from "react";

/** Ô soạn nội dung HÌNH NÀO RA HÌNH ĐÓ — `contentEditable`, không tab "Xem".
 *
 *  Khác `HtmlMathEditor` (textarea mã nguồn + tab xem trước): ở đây thẻ HTML được
 *  render ngay khi gõ nên không cần đối chiếu qua lại giữa hai tab.
 *
 *  Đánh đổi phải biết: trình duyệt CHUẨN HOÁ lại markup khi gõ (`<b>` có thể ra
 *  `<strong>`, thẻ rỗng bị dọn). Nội dung vẫn đúng nghĩa nhưng không còn y nguyên
 *  từng ký tự như bản chuyên gia dán vào. Muốn giữ nguyên tuyệt đối thì phải sửa
 *  ở chế độ mã nguồn (nút `</>`).
 *
 *  KHÔNG dùng `dangerouslySetInnerHTML` trên mỗi lần render: React sẽ ghi lại DOM
 *  và con trỏ nhảy về đầu ô sau mỗi chữ. Chỉ nạp HTML khi giá trị đến từ NGOÀI.
 */
export function SoanHtml({ value, onChange, placeholder, minHeight = 96, style }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  minHeight?: number;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cuoiRef = useRef(value);   // giá trị lần cuối CHÍNH Ô NÀY phát ra

  // Chỉ đồng bộ khi `value` khác thứ ô này vừa gửi lên (vd AI đổ nháp vào, mở bài
  // khác). Bỏ điều kiện này là con trỏ nhảy mỗi lần gõ.
  useEffect(() => {
    if (ref.current && value !== cuoiRef.current) {
      ref.current.innerHTML = value || "";
      cuoiRef.current = value;
    }
  }, [value]);

  const phat = () => {
    const html = ref.current?.innerHTML ?? "";
    cuoiRef.current = html;
    onChange(html);
  };

  const lenh = (c: string, v?: string) => {
    ref.current?.focus();
    // execCommand đã deprecated nhưng vẫn là cách duy nhất chạy ổn trên mọi trình
    // duyệt mà không kéo cả ProseMirror/TipTap vào (≈5 package).
    document.execCommand(c, false, v);
    phat();
  };

  return (
    <div className="sh" style={style}>
      <div className="sh-bar">
        <button type="button" title="Đậm (Ctrl+B)" onClick={() => lenh("bold")}><b>B</b></button>
        <button type="button" title="Nghiêng (Ctrl+I)" onClick={() => lenh("italic")}><i>I</i></button>
        <button type="button" title="Gạch chân" onClick={() => lenh("underline")}><u>U</u></button>
        <span className="sh-v" />
        <button type="button" title="Danh sách" onClick={() => lenh("insertUnorderedList")}>•—</button>
        <button type="button" title="Khối cần nhớ" onClick={() => lenh("formatBlock", "blockquote")}>❝</button>
        <span className="sh-v" />
        <button type="button" title="Xoá định dạng" onClick={() => lenh("removeFormat")}>⌫ᶠ</button>
        <span className="sh-ghi">công thức đặt trong $…$</span>
      </div>
      <div
        ref={ref}
        className="sh-o"
        style={{ minHeight }}
        contentEditable
        suppressContentEditableWarning
        data-rong={placeholder}
        onInput={phat}
        onBlur={phat}
        // Dán từ Word mang theo cả rừng style rác -> chỉ nhận văn bản thuần.
        onPaste={(e) => {
          e.preventDefault();
          const t = e.clipboardData.getData("text/plain");
          document.execCommand("insertText", false, t);
          phat();
        }}
      />
    </div>
  );
}
