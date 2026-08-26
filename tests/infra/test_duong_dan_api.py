"""Cấu hình proxy phải KHỚP router thật.

Đã mất hai lần với `/on-tap`: thiếu ở vite proxy (dev) rồi thiếu ở nginx (prod).
Cả hai lần triệu chứng giống nhau và vô dụng: route rơi xuống SPA, client nhận
index.html rồi báo "Không gọi được máy chủ", không có mã HTTP nào để lần.

Test này biến "quên sửa config" thành test đỏ.
"""
import re
from pathlib import Path

import pytest

from app.api import admin, auth, cms, lessons, tutor, video

GOC = Path(__file__).resolve().parents[2]


def _prefix_backend() -> set[str]:
    """Tiền tố cấp 1 của MỌI route backend, vd {"auth", "on-tap", ...}."""
    ra = set()
    for r in (auth, video, cms, lessons, tutor, admin):
        for route in r.router.routes:
            p = getattr(route, "path", "")
            if p.startswith("/"):
                ra.add(p.split("/")[1])
    ra.add("health")          # khai trong app/main.py, không thuộc router nào
    return ra


# MỖI khối server trên host có danh sách `location` RIÊNG. App học sinh và CMS ở
# hai domain khác nhau nên sửa một bên là bên kia vẫn chết — đúng cái đã xảy ra
# với /on-tap: sửa domain học sinh xong, CMS vẫn báo "Không gọi được máy chủ".
NGINX_HOST = ["nginx-dev-domain.conf.example", "nginx-admin-domain.conf.example"]


@pytest.mark.parametrize("ten", NGINX_HOST)
def test_nginx_prod_proxy_du_moi_tien_to(ten):
    """nginx trên host là CỬA DUY NHẤT — thiếu tiền tố nào là route đó chết."""
    conf = (GOC / "infra" / ten).read_text()
    m = re.search(r"location ~ \^/\(([^)]+)\)", conf)
    assert m, f"không tìm thấy location regex của API trong {ten}"
    co = set(m.group(1).split("|"))
    thieu = _prefix_backend() - co
    assert not thieu, (
        f"{ten} thiếu tiền tố: {sorted(thieu)}. "
        "Thêm vào location regex, không thì request rơi xuống SPA và trả HTML.")


def test_hai_khoi_nginx_dung_CUNG_danh_sach():
    """Lệch nhau là một domain chạy, domain kia chết — rất khó lần ra."""
    ds = []
    for ten in NGINX_HOST:
        conf = (GOC / "infra" / ten).read_text()
        ds.append(set(re.search(r"location ~ \^/\(([^)]+)\)", conf).group(1).split("|")))
    assert ds[0] == ds[1], f"lệch: {sorted(ds[0] ^ ds[1])}"


def _proxy_vite(f: Path) -> set[str]:
    return {m.group(1) for m in re.finditer(r'"/([a-z0-9-]+)":\s*"http', f.read_text())}


def _duong_dan_goi(f: Path) -> set[str]:
    """Tiền tố mà api.ts thật sự gọi — bắt cả req("/x") lẫn fetch(`${API_BASE}/x`)."""
    src = f.read_text()
    ra = {m.group(1) for m in re.finditer(r'req[<(][^"\'`]*[`"\']/([a-z0-9-]+)', src)}
    ra |= {m.group(1) for m in re.finditer(r'\$\{API_BASE\}/([a-z0-9-]+)', src)}
    return ra


@pytest.mark.parametrize("app_dir", ["web", "web-admin"])
def test_vite_proxy_du_cho_duong_dan_app_do_goi(app_dir):
    goi = _duong_dan_goi(GOC / app_dir / "src" / "api.ts")
    proxy = _proxy_vite(GOC / app_dir / "vite.config.ts")
    assert goi, f"không đọc được đường dẫn nào từ {app_dir}/src/api.ts"
    thieu = goi - proxy
    assert not thieu, (
        f"{app_dir}/vite.config.ts thiếu proxy cho: {sorted(thieu)} — "
        "dev sẽ nhận index.html thay vì JSON.")


def test_on_tap_co_trong_ca_hai_noi():
    """Chốt riêng đường dẫn đã gây sự cố ba lần (vite, nginx học sinh, nginx CMS)."""
    for ten in NGINX_HOST:
        conf = (GOC / "infra" / ten).read_text()
        assert "on-tap" in re.search(r"location ~ \^/\(([^)]+)\)", conf).group(1), ten
    for d in ("web", "web-admin"):
        assert "on-tap" in _proxy_vite(GOC / d / "vite.config.ts"), d
