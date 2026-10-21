"""US-26 — hàng rào cấu hình cho tiền tố `/de-giao` và setting `de_giao_daily_limit`.

Cùng tinh thần `test_duong_dan_api.py` / `test_compose_env.py` (thiếu một chỗ là route rơi xuống SPA,
hoặc .env trên server không tới được container). File riêng vì `app/api/de_giao.py` chưa tồn tại lúc
viết test RED: nhập nó ở đầu `test_duong_dan_api.py` sẽ làm đỏ cả file đang xanh. Khi DEV xong, nên
gộp `de_giao` vào `_prefix_backend()` của file đó (hợp đồng mục 5) — các test dưới đây vẫn đúng.
"""
import re
from pathlib import Path

import pytest
import yaml

from app.config import Settings

GOC = Path(__file__).resolve().parents[2]
NGINX_HOST = ["nginx-dev-domain.conf.example", "nginx-admin-domain.conf.example"]


def test_router_de_giao_co_that_va_gan_vao_app():
    """FastAPI mới không trải phẳng router con vào `app.routes` (là `_IncludedRouter`, không có
    `path`) nên kiểm qua schema OpenAPI của app — chính thứ client thấy."""
    from app.main import app
    from app.api import de_giao

    prefixes = {getattr(r, "path", "").split("/")[1] for r in de_giao.router.routes
                if getattr(r, "path", "").startswith("/")}
    assert prefixes == {"de-giao"}, prefixes
    paths = app.openapi()["paths"]
    assert any(p == "/de-giao" or p.startswith("/de-giao/") for p in paths), \
        "router chưa được include_router trong app/main.py"
    assert "/de-giao/vao" in paths and "/de-giao/xem-truoc" in paths


def test_router_de_giao_co_du_duong_theo_hop_dong():
    from app.api import de_giao

    co = {(m, r.path) for r in de_giao.router.routes for m in getattr(r, "methods", set())}
    can = {("POST", "/de-giao/xem-truoc"), ("POST", "/de-giao/{nhap_id}/cap-ma"),
           ("DELETE", "/de-giao/{nhap_id}"), ("GET", "/de-giao"), ("GET", "/de-giao/{id}"),
           ("GET", "/de-giao/{id}/ket-qua"), ("GET", "/de-giao/{id}/bai/{user_id}"),
           ("POST", "/de-giao/{id}/dong"), ("POST", "/de-giao/vao"), ("POST", "/de-giao/nop")}
    # Tên tham số đường dẫn là chi tiết cài đặt: so theo hình dạng (thay {...} bằng {}).
    def dang(s):
        return {(m, re.sub(r"\{[^}]+\}", "{}", p)) for m, p in s}
    thieu = dang(can) - dang(co)
    assert not thieu, f"thiếu route: {sorted(thieu)}"


@pytest.mark.parametrize("ten", NGINX_HOST)
def test_nginx_prod_proxy_tien_to_de_giao(ten):
    conf = (GOC / "infra" / ten).read_text()
    m = re.search(r"location ~ \^/\(([^)]+)\)", conf)
    assert m, f"không thấy location regex của API trong {ten}"
    assert "de-giao" in m.group(1).split("|"), (
        f"{ten} thiếu tiền tố de-giao — /de-giao/* rơi xuống SPA và trả HTML")


@pytest.mark.parametrize("app_dir", ["web", "web-admin"])
def test_vite_proxy_tien_to_de_giao(app_dir):
    src = (GOC / app_dir / "vite.config.ts").read_text()
    proxy = {m.group(1) for m in re.finditer(r'"/([a-z0-9-]+)":\s*"http', src)}
    assert "de-giao" in proxy, f"{app_dir}/vite.config.ts thiếu proxy /de-giao"


def test_setting_de_giao_daily_limit_mac_dinh_20():
    assert "de_giao_daily_limit" in Settings.model_fields
    assert Settings.model_fields["de_giao_daily_limit"].default == 20


def test_compose_api_chuyen_bien_de_giao_daily_limit_vao_container():
    conf = yaml.safe_load((GOC / "docker-compose.app.yml").read_text())
    env = conf["services"]["api"]["environment"]
    ten = set(env) if isinstance(env, dict) else {e.split("=")[0] for e in env}
    assert "DE_GIAO_DAILY_LIMIT" in ten, "docker-compose.app.yml (service api) thiếu DE_GIAO_DAILY_LIMIT"


def test_env_example_co_de_giao_daily_limit():
    assert re.search(r"^DE_GIAO_DAILY_LIMIT=", (GOC / ".env.example").read_text(), re.M)


def test_man_hinh_dang_ky_khong_con_chon_vai_kb38():
    """KB 38: màn hình đăng ký không có lựa chọn vai, và không gửi `role` khi đăng ký
    (web/src/components/LoginView.tsx — hợp đồng mục 1)."""
    src = (GOC / "web" / "src" / "components" / "LoginView.tsx").read_text()
    assert "login-roles" not in src, "còn khối chọn vai trên màn đăng ký"
    assert "register(email, password, name, role)" not in src
    assert 'value: "giao_vien"' not in src


def test_web_admin_req_xu_ly_204_truoc_khi_kiem_content_type_bug_qc26_01():
    """BUG QC26-01: `DELETE /de-giao/{id}` (huỷ bản nháp) trả 204 không thân bài, không có Content-Type.
    `req()` của web-admin kiểm `content-type` chứa "json" TRƯỚC khi xét 204 nên mọi 204 đều bị báo
    nhầm "Máy chủ trả nội dung không phải JSON ... route chưa được proxy" — nút "Huỷ" trên CMS hiện lỗi
    dù nháp đã bị xoá, bấm lần hai thì ra 404. Nhánh `res.status === 204` phải đứng trước phép kiểm."""
    src = (GOC / "web-admin" / "src" / "api.ts").read_text()
    thân = src[src.index("async function req"):]
    vi_tri_204 = thân.index("204")
    vi_tri_kieu = thân.index('kieu.includes("json")')
    assert vi_tri_204 < vi_tri_kieu, "req() còn kiểm content-type trước khi xử lý 204"
