import { useState } from "react";
import { ApiError, login, register } from "../api";
import { APP_NAME, TUTOR_NAME } from "../config";
import type { Role } from "../types";

export function LoginView({ onAuthed }: { onAuthed: () => void }) {
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
      if (mode === "login") await login(email, password);
      else await register(email, password, name, role);
      onAuthed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được máy chủ");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="brand">
          <img className="brand-logo" src="/dtp-logo.svg" alt="DTP" />
          <h1>{APP_NAME}</h1>
          <p className="brand-sub">Học cùng {TUTOR_NAME} — hỏi bài, giải bài bám sát SGK</p>
        </div>

        <div className="tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">
            Đăng nhập
          </button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">
            Đăng ký
          </button>
        </div>

        <form onSubmit={submit}>
          {mode === "register" && (
            <>
              <label>
                Tên của bé
                <input value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
              <label>
                Bạn là
                <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  <option value="hoc_sinh">Học sinh</option>
                  <option value="giao_vien">Giáo viên</option>
                </select>
              </label>
            </>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Mật khẩu
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>

          {error && <p className="error">{error}</p>}

          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
          </button>
        </form>
      </div>
    </div>
  );
}
