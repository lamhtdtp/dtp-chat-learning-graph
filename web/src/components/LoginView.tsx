import { useState } from "react";
import { ApiError, login, register } from "../api";
import { TUTOR_NAME } from "../config";
import { ThemeToggle } from "./ThemeToggle";
import type { Role } from "../types";

// Đăng nhập + chọn vai trò. 2 cột responsive (auth-screen tự xuống 1 cột ≤600px).
// Vai trò chỉ dùng khi ĐĂNG KÝ (đăng nhập lấy vai trò từ tài khoản).
export function LoginView({ onAuthed }: { onAuthed: (role: Role) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("hoc_sinh");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = mode === "login"
        ? await login(email, password)
        : await register(email, password, name, role);
      onAuthed(res.role);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được máy chủ");
    } finally {
      setBusy(false);
    }
  };

  const roleBtn = (value: Role, icon: string, title: string, desc: string) => (
    <button type="button" className={"role-btn" + (role === value ? " sel" : "")}
      data-subject="toan" onClick={() => setRole(value)} aria-pressed={role === value}>
      <span className="role-ic" aria-hidden>{icon}</span>
      <span>
        <span className="role-name">{title}</span>
        <span className="role-desc" style={{ display: "block" }}>{desc}</span>
      </span>
    </button>
  );

  return (
    <div className="auth-screen" data-subject="toan">
      <div className="auth-col-left">
        <div className="auth-card">
          <div className="auth-logo-row">
            <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
            <div>
              <div className="auth-title">{TUTOR_NAME}</div>
              <div className="auth-sub">Học đa môn cùng gia sư AI</div>
            </div>
            <div style={{ marginLeft: "auto" }}><ThemeToggle /></div>
          </div>

          <div className="auth-tabs">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Đăng nhập</button>
            <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Đăng ký</button>
          </div>

          {error && <div className="auth-error">{error}</div>}

          <form onSubmit={submit}>
            {mode === "register" && (
              <label>Họ và tên
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nguyễn Minh An" required />
              </label>
            )}
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ten@email.com" required />
            </label>
            <label>Mật khẩu
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            </label>
            <button className="auth-submit" type="submit" disabled={busy}>
              {busy ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
            </button>
          </form>
        </div>
      </div>

      <div className="auth-col-right">
        <div className="auth-card">
          <div className="role-title">Bạn là ai?</div>
          <div className="auth-sub" style={{ marginTop: -6 }}>
            {mode === "register" ? "Chọn vai trò để tạo tài khoản." : "Đăng nhập sẽ tự nhận vai trò của tài khoản."}
          </div>
          <div className="role-grid">
            {roleBtn("hoc_sinh", "🎒", "Học sinh", "Hỏi bài · xem video · luyện i-Test")}
            {roleBtn("giao_vien", "👩‍🏫", "Giáo viên", "Sinh đề theo ma trận · ngân hàng câu hỏi")}
          </div>
        </div>
        <div className="a11y-note">
          Giao diện đa môn, hỗ trợ sáng/tối, tương phản đạt WCAG AA, thao tác được bằng bàn phím.
        </div>
      </div>
    </div>
  );
}
