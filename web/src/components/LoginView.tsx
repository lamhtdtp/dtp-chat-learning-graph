import { useState } from "react";
import { ApiError, login, register } from "../api";
import { TUTOR_NAME } from "../config";
import { ThemeToggle } from "./ThemeToggle";
import type { Role } from "../types";

const ROLES: { value: Role; icon: string; title: string; desc: string }[] = [
  { value: "hoc_sinh", icon: "🎒", title: "Học sinh", desc: "Hỏi bài · xem video · luyện i-Test" },
  { value: "giao_vien", icon: "👩‍🏫", title: "Giáo viên", desc: "Sinh đề theo ma trận · ngân hàng câu hỏi" },
];

// Ký hiệu học thuật bay ở hero (đa môn: toán + ngôn ngữ + khoa học).
const SYMBOLS = [
  { s: "÷", style: { top: "9%", right: "13%", fontSize: 116 }, r: "-8deg", dur: "7s" },
  { s: "×", style: { bottom: "15%", left: "7%", fontSize: 140 }, r: "10deg", dur: "9s" },
  { s: "√", style: { top: "45%", right: "8%", fontSize: 86 }, r: "6deg", dur: "8s" },
  { s: "π", style: { top: "24%", left: "13%", fontSize: 70 }, r: "-5deg", dur: "6.4s" },
  { s: "A", style: { bottom: "30%", right: "20%", fontSize: 74 }, r: "8deg", dur: "7.6s" },
];

const FEATS = [
  { ic: "📚", t: "Bám sát SGK" },
  { ic: "✏️", t: "Giải thích từng bước" },
  { ic: "🎬", t: "Video minh hoạ" },
  { ic: "📝", t: "Luyện tập i-Test" },
];

// Trang đăng nhập kiểu hero split-screen (tham chiếu bản home cũ) — nền gradient
// + form bên phải; đa môn, theo token mới, sáng/tối, responsive (≤900px ẩn hero).
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
      <aside className="auth-hero">
        {SYMBOLS.map((x, i) => (
          <span key={i} className="hero-sym"
            style={{ ...x.style, ["--r" as string]: x.r, animationDuration: x.dur }}>
            {x.s}
          </span>
        ))}
        <div className="hero-top">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div>
            <div className="name">{TUTOR_NAME}</div>
            <div className="sub">Học đa môn cùng gia sư AI</div>
          </div>
        </div>
        <div className="hero-center">
          <div className="hero-badge" aria-hidden>🎓</div>
          <div className="hero-title">Học thông minh<br />cùng {TUTOR_NAME}</div>
          <div className="hero-desc">
            Gia sư ảo đa môn bám sát sách giáo khoa — giải thích từng bước, trích
            dẫn đúng trang sách, video minh hoạ và luyện tập mỗi ngày.
          </div>
        </div>
        <div className="hero-feats">
          {FEATS.map((f, i) => (
            <div className="feat" key={i}><span className="ic" aria-hidden>{f.ic}</span> {f.t}</div>
          ))}
        </div>
      </aside>

      <main className="auth-panel">
        <div className="auth-panel-top"><ThemeToggle /></div>
        <div className="auth-mobilebrand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <span className="t">{TUTOR_NAME}</span>
        </div>

        <div className="auth-card">
          <div>
            <div className="auth-hi">Xin chào! 👋</div>
            <div className="auth-hi-sub">
              {mode === "login" ? `Đăng nhập để tiếp tục học cùng ${TUTOR_NAME}.` : "Tạo tài khoản để bắt đầu học."}
            </div>
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
                        <button key={r.value} type="button" role="radio" aria-checked={sel}
                          tabIndex={sel ? 0 : -1} className={"role-btn" + (sel ? " sel" : "")}
                          onClick={() => setRole(r.value)}>
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
      </main>
    </div>
  );
}
