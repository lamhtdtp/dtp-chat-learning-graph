import { useEffect, useRef, useState } from "react";
import { ApiError, dangNhapKhongLuu, getMe, tokenStore, xinSsoTestbank } from "../api";
import { TUTOR_NAME } from "../config";
import type { Role } from "../types";
import { useTheme } from "../hooks/useTheme";
import "./login.css";

/** Đường vào của nút "Đăng nhập bằng tài khoản Gia sư DTP" trên trang đăng nhập Testbank:
 *  `/sso/testbank?quay_ve=<địa chỉ /sso của Testbank>` (T8).
 *
 *  Màn này CHỈ dành cho thầy cô. Phiên thầy cô / chuyên gia / admin đang có thì đi thẳng; không có
 *  phiên hoặc phiên là học sinh thì hiện form đăng nhập riêng (không tab Đăng ký, không nhắc gì tới
 *  phiên học sinh). Token lấy từ form chỉ giữ trong bộ nhớ, KHÔNG ghi localStorage — ghi vào là đè
 *  mất phiên học sinh của máy dùng chung. `quay_ve` chỉ được GỬI cho máy chủ để kiểm; trang không
 *  bao giờ chuyển hướng tới nó — địa chỉ "Về Testbank" và địa chỉ phiếu đều do máy chủ trả (dựng từ
 *  cấu hình), nên một `quay_ve` giả không dắt được ai tới trang lạ. */
export const DUONG_SSO_TESTBANK = "/sso/testbank";

const THAY_CO: Role[] = ["giao_vien", "chuyen_gia", "admin"];
const MSG_LA_HS = "Đây là tài khoản học sinh, thầy cô đăng nhập bằng tài khoản giáo viên nhé.";

type TrangThai =
  | { k: "cho" }
  | { k: "dang_nhap" }
  | { k: "chuyen" }
  | { k: "tat"; ve: string }
  | { k: "loi"; message: string; ve: string | null };

export function SsoTestbankView() {
  useTheme();
  const [tt, setTt] = useState<TrangThai>({ k: "cho" });
  const [loiForm, setLoiForm] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  // StrictMode chạy effect hai lần: mỗi lần gọi là một phiếu cấp ra, nên chỉ gọi một lần.
  const daGoi = useRef(false);

  /** `token` = token giáo viên từ form (trong bộ nhớ); không có thì dùng phiên đã lưu. */
  const xinPhieu = async (token?: string) => {
    const quayVe = new URLSearchParams(window.location.search).get("quay_ve");
    const r = await xinSsoTestbank(quayVe, token);
    if (r.loai === "chuyen") {
      setTt({ k: "chuyen" });
      window.location.replace(r.url); // phiếu chỉ ở sau `#`, và replace để Back không quay lại màn này
    } else if (r.loai === "dang_nhap") setTt({ k: "tat", ve: r.veTestbank });
    else if (r.status === 401) { setLoiForm("Phiên đăng nhập không hợp lệ, thầy cô đăng nhập lại nhé."); setTt({ k: "dang_nhap" }); }
    else setTt({ k: "loi", message: r.message, ve: r.veTestbank });
  };

  const chay = async () => {
    // Không xoá token đã lưu ở bất cứ nhánh nào: đó có thể là phiên học sinh của app chính.
    if (!tokenStore.get()) { setTt({ k: "dang_nhap" }); return; }
    let vai: Role;
    try { vai = (await getMe()).role; } catch { setTt({ k: "dang_nhap" }); return; }
    if (!THAY_CO.includes(vai)) { setTt({ k: "dang_nhap" }); return; }
    await xinPhieu();
  };

  useEffect(() => {
    if (daGoi.current) return;
    daGoi.current = true;
    void chay();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoiForm(null);
    setBusy(true);
    try {
      const res = await dangNhapKhongLuu(email, password);
      if (!THAY_CO.includes(res.role)) { setLoiForm(MSG_LA_HS); return; }
      await xinPhieu(res.token);
    } catch (err) {
      setLoiForm(err instanceof ApiError ? err.message : "Không kết nối được máy chủ");
    } finally {
      setBusy(false);
    }
  };

  const khung = (children: React.ReactNode) => (
    <div className="login" style={{ gridTemplateColumns: "1fr" }}>
      <main className="login-main">{children}</main>
    </div>
  );

  const hop = (tieuDe: string, noiDung: string, nut: { nhan: string; href: string } | null, loi = false) =>
    khung(
      <div className="login-card" role={loi ? "alert" : "status"}>
        <div className="login-hi">{tieuDe}</div>
        <div className="login-hi-sub">{noiDung}</div>
        {nut && <a className="login-submit" style={{ textAlign: "center", textDecoration: "none" }}
                   href={nut.href}>{nut.nhan}</a>}
      </div>,
    );

  switch (tt.k) {
    case "dang_nhap":
      return khung(
        <div className="login-card">
          <div>
            <div className="login-hi">Đăng nhập tài khoản thầy cô để vào Testbank</div>
            <div className="login-hi-sub">Dùng tài khoản giáo viên của {TUTOR_NAME}.</div>
          </div>
          {loiForm && <div className="login-err" role="alert">⚠️ {loiForm}</div>}
          <form className="login-form" onSubmit={submit}>
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ten@email.com" required />
            </label>
            <label>Mật khẩu
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            </label>
            <button className="login-submit" type="submit" disabled={busy}>
              {busy ? "Đang xử lý…" : "Đăng nhập"}
            </button>
          </form>
        </div>,
      );
    case "tat":
      return hop("Testbank chưa nhận đăng nhập từ " + TUTOR_NAME,
        "Thầy cô đăng nhập Testbank bằng mật khẩu của Testbank nhé.", { nhan: "Về Testbank", href: tt.ve });
    case "loi":
      return hop("Chưa mở được Testbank", tt.message,
        tt.ve ? { nhan: "Về Testbank", href: tt.ve } : { nhan: "Về trang chính", href: "/" }, true);
    default:
      return hop("Đang mở Testbank…", "Thầy cô chờ một chút nhé.", null);
  }
}
