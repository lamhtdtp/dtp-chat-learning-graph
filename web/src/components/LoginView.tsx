import { useState } from "react";
import { ApiError, login, register } from "../api";
import { TUTOR_NAME } from "../config";
import { ThemeToggle } from "./ThemeToggle";
import type { Role } from "../types";

const ROLES: { value: Role; icon: string; title: string; desc: string }[] = [
  { value: "hoc_sinh", icon: "🎒", title: "Học sinh", desc: "Hỏi bài · xem video · luyện i-Test" },
  { value: "giao_vien", icon: "👩‍🏫", title: "Giáo viên", desc: "Sinh đề theo ma trận · ngân hàng câu hỏi" },
];

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

  // Radiogroup đúng chuẩn: mũi tên di chuyển lựa chọn, roving tabindex (chỉ ô
  // đang chọn nhận Tab), aria-checked + dấu ✓ để rõ trạng thái (WCAG AA).
  const onRoleKey = (e: React.KeyboardEvent) => {
    const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    const idx = ROLES.findIndex((r) => r.value === role);
    const fwd = e.key === "ArrowDown" || e.key === "ArrowRight";
    setRole(ROLES[(idx + (fwd ? 1 : ROLES.length - 1)) % ROLES.length].value);
  };

  return (
    <div className="auth-screen" data-subject="toan">
      <div className="auth-card auth-single">
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
            <>
              <label>Họ và tên
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nguyễn Minh An" required />
              </label>
              <div className="role-field">
                <div className="role-field-label">Bạn là ai?</div>
                <div className="role-grid" role="radiogroup" aria-label="Vai trò tài khoản" onKeyDown={onRoleKey}>
                  {ROLES.map((r) => {
                    const sel = role === r.value;
                    return (
                      <button
                        key={r.value}
                        type="button"
                        role="radio"
                        aria-checked={sel}
                        tabIndex={sel ? 0 : -1}
                        className={"role-btn" + (sel ? " sel" : "")}
                        onClick={() => setRole(r.value)}
                      >
                        <span className="role-ic" aria-hidden>{r.icon}</span>
                        <span className="role-txt">
                          <span className="role-name">{r.title}</span>
                          <span className="role-desc">{r.desc}</span>
                        </span>
                        <span className="role-check" aria-hidden>✓</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </>
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

        <div className="auth-foot">
          {mode === "login" ? (
            <>Chưa có tài khoản?{" "}
              <button type="button" className="auth-link" onClick={() => setMode("register")}>Đăng ký ngay</button>
            </>
          ) : (
            <>Đã có tài khoản?{" "}
              <button type="button" className="auth-link" onClick={() => setMode("login")}>Đăng nhập</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
