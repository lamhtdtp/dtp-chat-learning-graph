"""Bóc JSON từ câu trả lời LLM, chịu được lỗi escape do LaTeX.

Nội dung Toán bám SGK đầy công thức ($\\mathbb{N}$, $\\frac{a}{b}$, $\\neq$…).
Khi model nhét chúng vào chuỗi JSON, nó phải nhân đôi dấu gạch chéo ngược
(`\\\\frac`); chỉ cần một lần quên là `\\f`, `\\m`, `\\n` thành escape không hợp
lệ và json.loads ném lỗi cho CẢ tài liệu — mất trắng bài đã soạn xong.

Hàm ở đây vá đúng lỗi đó rồi thử lại, thay vì bỏ cả kết quả.
"""
import json
import logging
import re

log = logging.getLogger(__name__)

# Vá lệnh LaTeX bị nuốt. Thứ tự alternation là điểm mấu chốt:
#   1. `\\` + bất kỳ  -> đã escape đúng, ăn cả cặp, giữ nguyên (không thì `\\frac`
#      đúng sẵn lại bị nhân đôi tiếp).
#   2. `\` + TỪ 2 CHỮ CÁI trở lên -> lệnh LaTeX (\frac, \neq, \times, \mathbb)
#      -> nhân đôi dấu gạch chéo.
#   3. còn lại (`\n`, `\t` đứng lẻ, `\"`, `\/`, `\uXXXX`) -> escape JSON thật, giữ.
#
# Vì sao phải chạy LUÔN chứ không đợi json.loads lỗi: `\f`, `\b`, `\n`, `\t` ĐỀU
# là escape JSON hợp lệ, nên `\frac` `\beta` `\neq` `\times` parse "thành công"
# thành formfeed/backspace/xuống dòng/tab + phần đuôi. Không lỗi, chỉ âm thầm
# nát công thức — đúng những lệnh Toán 6 hay dùng nhất.
# Chỉ vá khi từ đứng sau là LỆNH LaTeX ĐÃ BIẾT. Đoán theo hình dạng ("\ + từ 2
# chữ cái trở lên") thì `"dòng1\ndòng2"` — xuống dòng thật rồi tới chữ — bị hiểu
# nhầm thành lệnh `\ndòng2`, biến ký tự xuống dòng thành chữ "\n" hiện ra màn
# hình. Danh sách đủ phủ Toán THCS; lệnh lạ ngoài danh sách thì chịu, nhưng thà
# bỏ sót còn hơn phá văn bản tiếng Việt bình thường.
_LENH = (
    "frac", "dfrac", "sqrt", "times", "div", "cdot", "pm", "mp", "neq", "leq", "geq",
    "le", "ge", "approx", "equiv", "infty", "ldots", "dots", "cdots", "overline",
    "underline", "widehat", "hat", "vec", "mathbb", "mathrm", "mathbf", "text",
    "left", "right", "begin", "end", "angle", "triangle", "circ", "degree", "perp",
    "parallel", "in", "notin", "subset", "supset", "cup", "cap", "emptyset", "varnothing",
    "forall", "exists", "alpha", "beta", "gamma", "delta", "theta", "lambda", "mu",
    "pi", "sigma", "omega", "Delta", "Omega", "quad", "qquad", "displaystyle",
    "sum", "prod", "int", "lim", "min", "max", "mid", "to", "rightarrow", "Rightarrow",
    "leftrightarrow", "Leftrightarrow", "boxed", "binom", "percent",
)
_LATEX = re.compile(r"\\\\.|\\([A-Za-z]+)")


def _la_lenh(tu: str) -> bool:
    """`tu` bắt đầu bằng một lệnh đã biết? (`frac` trong `\\frac`, và `neq` trong
    `\\neq b` vì regex đã cắt ở khoảng trắng)."""
    return any(tu.startswith(l) for l in _LENH)


def va_latex(text: str) -> str:
    def _fix(m: re.Match) -> str:
        tu = m.group(1)
        return m.group(0) if tu is None or not _la_lenh(tu) else "\\\\" + tu
    return _LATEX.sub(_fix, text)


def boc_json(raw: str) -> object | None:
    """Trả object JSON, hoặc None nếu chịu thua. Ghi log khi phải vá / khi hỏng."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    va = va_latex(text)
    try:
        return json.loads(va)
    except json.JSONDecodeError as e:
        try:
            return json.loads(text)   # bản vá làm hỏng thêm -> quay về nguyên bản
        except json.JSONDecodeError:
            # Log cả đoạn đầu: im lặng trả rỗng khiến lỗi này ẩn rất lâu.
            log.warning("Không bóc được JSON từ LLM (%s). 300 ký tự đầu: %r", e, text[:300])
            return None
