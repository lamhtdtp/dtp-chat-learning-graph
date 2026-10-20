"""Chữ của testbank -> HTML an toàn cho trình duyệt, hoặc văn bản thuần cho prompt.

Đề bài, phương án, lời giải của testbank là chữ có thể kèm HTML đơn giản (`<u>`,
`<strong>`, `<p>`) và dấu ảnh ngay trong chữ: `[[anh:<32 hex>]]` hoặc
`[[anh:<id>|w=<point>]]`. Công thức gõ bằng Equation đã thành Unicode, còn công
thức dạng ảnh vẫn là ảnh — ở kho Toán 6 thật, phần lớn công thức là ảnh.

Chuỗi ra đi thẳng vào `dangerouslySetInnerHTML`, mà kho có người nhập tay từ
Word. Nên: thoát hết, rồi chỉ mở lại đúng vài thẻ định dạng KHÔNG thuộc tính.
"""
import html
import re

# Biểu thức chép từ tài liệu tích hợp của testbank (§6).
_DAU_ANH = re.compile(r"\[\[anh:([0-9a-f]{32})(?:\|w=(\d{1,4}(?:\.\d{1,2})?))?\]\]")
# Thẻ được giữ — sau khi đã thoát, nên khớp trên dạng &lt;…&gt;. Chỉ thẻ trần,
# không thuộc tính: `<p onclick=…>` không khớp, ở lại dạng chữ.
_THE_CHO_PHEP = re.compile(r"&lt;(/?)(p|u|b|i|em|strong|sub|sup|br\s*/?)&gt;", re.IGNORECASE)
# Thẻ bảng — đề có bảng số liệu ("Tiền lời từng ngày…"). Thuộc tính chỉ giữ
# colspan/rowspan dạng SỐ, dựng lại thẻ từ đầu nên mọi thứ khác (onclick, style)
# rơi mất chứ không lọt qua.
_THE_BANG = re.compile(
    r"&lt;(/?)(table|thead|tbody|tfoot|tr|td|th)((?:\s(?:(?!&gt;).)*)?)&gt;", re.IGNORECASE)
_O_GOP = re.compile(r"\b(colspan|rowspan)\s*=\s*(?:&quot;|&#x27;)?(\d{1,2})(?:&quot;|&#x27;)?",
                    re.IGNORECASE)
# Khoảng trắng / <br> / &nbsp; nằm GIỮA các thẻ cấu trúc bảng (không phải trong ô)
# là nút chữ trong <table>: trình duyệt đẩy nó ra ngoài, thành dòng trống trên bảng.
_RAC_GIUA_BANG = re.compile(
    r"(<(?:/?(?:table|thead|tbody|tfoot|tr)|/t[dh])\b[^>]*>)(?:\s|&nbsp;|<br>)+"
    r"(?=</?(?:table|thead|tbody|tfoot|tr|td|th)\b)")
_THE_BAT_KY = re.compile(r"<[^>]+>")
_TIEN_TO_CONG = "/api/content"
# Word đo bằng point, trình duyệt bằng px (96/72).
_PT_SANG_PX = 4 / 3


def co_anh(s: str | None) -> bool:
    return bool(s) and _DAU_ANH.search(s) is not None


def url_anh(url: str, goc: str) -> str:
    """URL ảnh testbank trả -> URL trình duyệt mở được.

    Hiện testbank trả đường TƯƠNG ĐỐI `/api/content/media/…`, nhưng môi trường
    khác có thể trả tuyệt đối (CDN) — gặp thật ngay ở dữ liệu dev: một câu lẫn
    cả hai loại. Tương đối thì thay tiền tố cổng `/api/content` bằng `goc` (gốc
    content-service): đúng cho prod (cùng cổng, `goc` đã gồm tiền tố) lẫn máy
    dev (content chạy riêng cổng, không tiền tố)."""
    if url.startswith(("http://", "https://")):
        return url
    duoi = url[len(_TIEN_TO_CONG):] if url.startswith(_TIEN_TO_CONG + "/") else url
    return goc.rstrip("/") + "/" + duoi.lstrip("/")


def _the_bang(m: re.Match) -> str:
    dong, ten = m.group(1), m.group(2).lower()
    if dong or ten not in ("td", "th"):
        return f"<{dong}{ten}>"
    attrs = "".join(f' {a.lower()}="{n}"' for a, n in _O_GOP.findall(m.group(3) or ""))
    return f"<{ten}{attrs}>"


def sang_html(text: str | None, assets: dict[str, str], sizes: dict[str, dict],
              *, goc: str) -> str:
    """Chữ testbank -> HTML an toàn. `assets`/`sizes` lấy nguyên từ
    `questions:resolve` của chính câu đó."""
    if not text:
        return ""
    s = html.escape(text.replace("\r\n", "\n"), quote=True)
    s = _THE_CHO_PHEP.sub(lambda m: f"<{m.group(1)}{m.group(2).lower().replace(' ', '')}>", s)
    s = _THE_BANG.sub(_the_bang, s)
    # Đề canh "Hình 1      Hình 2" dưới ảnh bằng khoảng trắng: gộp lại là lệch nhãn.
    s = re.sub(r" {2,}", lambda m: " " + "&nbsp;" * (len(m.group(0)) - 1), s)
    s = s.replace("\n", "<br>")
    s = _RAC_GIUA_BANG.sub(r"\1", s)

    def _anh(m: re.Match) -> str:
        id_, w = m.group(1), m.group(2)
        url = assets.get(id_)
        if not url:
            # Ảnh của đáp án/lời giải chỉ có khi include_answers. Để lại dấu thô
            # là học sinh thấy "[[anh:3f2a…]]" giữa đề.
            return '<span class="tb-thieu-anh">[thiếu hình]</span>'
        kich = sizes.get(id_) or {}
        goc_w, goc_h = float(kich.get("w") or 0), float(kich.get("h") or 0)
        rong = float(w) if w else goc_w
        style = f' style="width:{round(rong * _PT_SANG_PX)}px"' if rong > 0 else ""
        # Ảnh chưa tải xong có chiều cao 0 -> phương án trống rồi cả trang giật khi ảnh về.
        # Server biết kích thước gốc nên ghi luôn width/height (giữ tỉ lệ, kể cả khi
        # `|w=` đổi chiều rộng): với CSS `max-width:100%;height:auto`, trình duyệt dùng
        # cặp này làm tỉ lệ khung nên co nhỏ vẫn không méo.
        wh = ""
        if rong > 0 and goc_w > 0 and goc_h > 0:
            wh = (f' width="{round(rong * _PT_SANG_PX)}"'
                  f' height="{round(goc_h * rong / goc_w * _PT_SANG_PX)}"')
        return (f'<img class="tb-anh" src="{html.escape(url_anh(url, goc), quote=True)}" '
                f'alt=""{wh}{style}>')

    return _DAU_ANH.sub(_anh, s)


def sang_van_ban(text: str | None) -> str:
    """Chữ testbank -> văn bản thuần cho prompt: bỏ thẻ, ảnh thành "[hình]"."""
    s = _DAU_ANH.sub("[hình]", text or "")
    s = _THE_BAT_KY.sub("", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()
