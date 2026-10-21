import { useEffect, useRef, useState } from "react";
import { getMe, tokenStore, xinSsoTestbank } from "../api";
import { TUTOR_NAME } from "../config";
import type { Role } from "../types";
import { useTheme } from "../hooks/useTheme";
import { LoginView } from "./LoginView";
import "./login.css";

/** Đường vào của nút "Đăng nhập bằng tài khoản Gia sư DTP" trên trang đăng nhập Testbank:
 *  `/sso/testbank?quay_ve=<địa chỉ /sso của Testbank>` (T8).
 *
 *  Chưa đăng nhập: hiện form đăng nhập ngay tại đường này (không đổi URL) nên đăng nhập xong
 *  query còn nguyên. `quay_ve` chỉ được GỬI cho máy chủ để kiểm; trang không bao giờ chuyển
 *  hướng tới nó — địa chỉ "Về Testbank" và địa chỉ phiếu đều do máy chủ trả (dựng từ cấu hình),
 *  nên một `quay_ve` giả không dắt được ai tới trang lạ. */
export const DUONG_SSO_TESTBANK = "/sso/testbank";

const THAY_CO: Role[] = ["giao_vien", "chuyen_gia", "admin"];
const MSG_HS = "Chỉ thầy cô dùng được Testbank";

type TrangThai =
  | { k: "cho" }
  | { k: "dang_nhap" }
  | { k: "hoc_sinh" }
  | { k: "chuyen" }
  | { k: "tat"; ve: string }
  | { k: "loi"; message: string; ve: string | null };

export function SsoTestbankView() {
  useTheme();
  const [tt, setTt] = useState<TrangThai>({ k: "cho" });
  // StrictMode chạy effect hai lần: mỗi lần gọi là một phiếu cấp ra, nên chỉ gọi một lần.
  const daGoi = useRef(false);

  const chay = async () => {
    if (!tokenStore.get()) { setTt({ k: "dang_nhap" }); return; }
    let vai: Role;
    try { vai = (await getMe()).role; } catch { tokenStore.clear(); setTt({ k: "dang_nhap" }); return; }
    if (!THAY_CO.includes(vai)) { setTt({ k: "hoc_sinh" }); return; }
    const quayVe = new URLSearchParams(window.location.search).get("quay_ve");
    const r = await xinSsoTestbank(quayVe);
    if (r.loai === "chuyen") {
      setTt({ k: "chuyen" });
      window.location.replace(r.url); // phiếu chỉ ở sau `#`, và replace để Back không quay lại màn này
    } else if (r.loai === "dang_nhap") setTt({ k: "tat", ve: r.veTestbank });
    else if (r.status === 401) { tokenStore.clear(); setTt({ k: "dang_nhap" }); }
    else setTt({ k: "loi", message: r.message, ve: r.veTestbank });
  };

  useEffect(() => {
    if (daGoi.current) return;
    daGoi.current = true;
    void chay();
  }, []);

  if (tt.k === "dang_nhap") return <LoginView onAuthed={() => { setTt({ k: "cho" }); void chay(); }} />;

  const hop = (tieuDe: string, noiDung: string, nut: { nhan: string; href: string } | null, loi = false) => (
    <div className="login" style={{ gridTemplateColumns: "1fr" }}>
      <main className="login-main">
        <div className="login-card" role={loi ? "alert" : "status"}>
          <div className="login-hi">{tieuDe}</div>
          <div className="login-hi-sub">{noiDung}</div>
          {nut && <a className="login-submit" style={{ textAlign: "center", textDecoration: "none" }}
                     href={nut.href}>{nut.nhan}</a>}
        </div>
      </main>
    </div>
  );

  switch (tt.k) {
    case "hoc_sinh":
      return hop(MSG_HS, "Tài khoản học sinh làm bài ngay trên " + TUTOR_NAME + ".", { nhan: "Về trang chính", href: "/" }, true);
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
