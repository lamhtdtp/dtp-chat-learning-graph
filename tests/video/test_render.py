import shutil

import pytest

from app.video.render import KaTeXError, katex_validate, render_slide
from app.video.script import Slide

_HAS_NODE = shutil.which("node") is not None


@pytest.mark.skipif(not _HAS_NODE, reason="cần node + katex")
def test_katex_validate_cong_thuc_hop_le():
    html = katex_validate("a \\cdot b = b \\cdot a")
    assert "katex" in html  # KaTeX xuất HTML có class katex


@pytest.mark.skipif(not _HAS_NODE, reason="cần node + katex")
def test_katex_validate_chan_cu_phap_sai():
    with pytest.raises(KaTeXError):
        katex_validate("\\frac{1}{")  # thiếu ngoặc -> vỡ công thức


def test_render_slide_deterministic(tmp_path):
    slide = Slide(tieu_de="Số nguyên tố", y_chinh=["Chỉ có 2 ước"], cong_thuc=[], loi_thoai="x")
    a = render_slide(slide, tmp_path / "a.png", index=0, total=2)
    b = render_slide(slide, tmp_path / "b.png", index=0, total=2)
    # Cùng kịch bản -> slide giống hệt (US-18 Scenario 1).
    assert a.read_bytes() == b.read_bytes()


def test_render_slide_tao_png(tmp_path):
    slide = Slide(tieu_de="Lũy thừa", y_chinh=["a mũ n"], cong_thuc=["2^3=8"], loi_thoai="x")
    out = render_slide(slide, tmp_path / "s.png", index=1, total=3)
    assert out.is_file() and out.stat().st_size > 0
