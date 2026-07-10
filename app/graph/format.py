"""Chỉ dẫn định dạng công thức dùng chung cho các node sinh câu trả lời.

Frontend render KaTeX cho công thức đặt giữa `$...$` (xem web/src/markdown.tsx).
Ép model LUÔN bọc công thức trong `$...$` để hiển thị đúng như công thức toán,
tránh LaTeX trần / `\\( \\)` / `\\[ \\]` mà frontend không nhận ra.
"""

MATH_FORMAT = (
    r"Viết MỌI công thức và ký hiệu toán dưới dạng LaTeX đặt giữa dấu $...$ "
    r"(ví dụ $\mathbb{Z}$, $\dfrac{1}{2}$, $-3 < 0$, $2^3 = 8$) để hiển thị đúng "
    r"như công thức toán. KHÔNG dùng \( \), \[ \] hay để công thức trần ngoài $...$."
)
