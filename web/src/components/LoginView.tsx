import { useState } from "react";
import { ApiError, login, register } from "../api";
import { APP_NAME, TUTOR_NAME } from "../config";
import type { Role } from "../types";

const SYMBOLS = [
  { s: "÷", style: { top: "8%", right: "12%", fontSize: 120, opacity: 0.1 }, r: "-8deg", dur: "7s" },
  { s: "×", style: { bottom: "16%", left: "8%", fontSize: 140, opacity: 0.09 }, r: "10deg", dur: "9s" },
  { s: "√", style: { top: "44%", right: "7%", fontSize: 88, opacity: 0.1 }, r: "6deg", dur: "8s" },
  { s: "π", style: { top: "24%", left: "14%", fontSize: 70, opacity: 0.1 }, r: "-5deg", dur: "6.4s" },
];

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
      <div className="auth-hero">
        {SYMBOLS.map((x, i) => (
          <span key={i} className="hero-sym" style={{ ...x.style, ["--r" as string]: x.r, animationDuration: x.dur }}>
            {x.s}
          </span>
        ))}

        <div className="hero-brand">
          <div className="hero-logo-box">
            <img src="/dtp-logo.png" alt="DTP" />
          </div>
          <div>
            <div className="name">DTP</div>
            <div className="sub">{APP_NAME}</div>
          </div>
        </div>

        <div className="hero-center">
          <div className="hero-badge" aria-hidden>🎓</div>
          <div className="hero-title">Học Toán thông minh<br />cùng {TUTOR_NAME}</div>
          <div className="hero-desc">
            Gia sư ảo bám sát sách giáo khoa — giải thích từng bước, trích dẫn đúng
            trang sách, và đồng hành cùng bạn mỗi ngày.
          </div>
        </div>

        <div className="hero-feats">
          <div className="feat"><span className="ic">📘</span> Bám sát SGK</div>
          <div className="feat"><span className="ic">✏️</span> Giải thích từng bước</div>
          <div className="feat"><span className="ic">📝</span> Trích dẫn số trang</div>
        </div>
      </div>

      <div className="auth-panel">
        <div className="auth-col">
          <div className="mobile-brand">
            <div className="box"><img src="/dtp-logo.png" alt="DTP" /></div>
            <div className="t">DTP · {APP_NAME}</div>
          </div>

          <div className="auth-card">
            <div>
              <div className="hi">Xin chào! 👋</div>
              <div className="hi-sub">
                {mode === "login" ? `Đăng nhập để tiếp tục học cùng ${TUTOR_NAME}.` : "Tạo tài khoản để bắt đầu."}
              </div>
            </div>

            <div className="tabs">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Đăng nhập</button>
              <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Đăng ký</button>
            </div>

            {error && <div className="error">{error}</div>}

            <form onSubmit={submit}>
              {mode === "register" && (
                <div className="row2">
                  <label style={{ flex: 1 }}>
                    Họ và tên
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nguyễn Minh An" required />
                  </label>
                  <label style={{ width: 130 }}>
                    Vai trò
                    <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                      <option value="hoc_sinh">Học sinh</option>
                      <option value="giao_vien">Giáo viên</option>
                    </select>
                  </label>
                </div>
              )}
              <label>
                Email
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ten@email.com" required />
              </label>
              <label>
                Mật khẩu
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
              </label>
              <button className="btn-primary" type="submit" disabled={busy}>
                {busy ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
