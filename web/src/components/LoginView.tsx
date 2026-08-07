import { useState } from "react";
import { ApiError, login, register } from "../api";
import { TUTOR_NAME } from "../config";
import { useTheme } from "../hooks/useTheme";
import type { Role } from "../types";
import "./login.css";

const ROLES: { value: Role; icon: string; title: string; desc: string }[] = [
  { value: "hoc_sinh", icon: "🎒", title: "Học sinh", desc: "Học theo mục lục · kiểm tra nhanh · trợ lý AI" },
  { value: "giao_vien", icon: "👩‍🏫", title: "Giáo viên", desc: "Slide giảng dạy · hướng dẫn dạy từng bài" },
];

// Tính năng THẬT của bản giáo trình (bỏ i-Test/video/trích trang cũ).
const FEATS = [
  { ic: "📚", t: "Bài học bám chương trình, 4 phần rõ ràng" },
  { ic: "✅", t: "Kiểm tra nhanh sau mỗi đơn vị kiến thức" },
  { ic: "💬", t: "Trợ lý hỏi–đáp trả lời bám sách giáo khoa" },
  { ic: "🔥", t: "Theo dõi tiến độ, chuỗi ngày học & điểm XP" },
];

// Trang đăng nhập split-screen: hero gradient (trái) + form (phải). Đồng bộ design
// bên trong (tím/cam/teal, serif), sáng/tối theo data-theme, ≤900px ẩn hero.
export function LoginView({ onAuthed }: { onAuthed: (role: Role) => void }) {
  const { cycle, icon, label } = useTheme();
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

  return (
    <div className="login">
      <aside className="login-hero">
        <div className="login-brand">
          <div className="logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div><b>{TUTOR_NAME}</b><span>Nền tảng học Toán 6 có lộ trình</span></div>
        </div>
        <div className="login-hero-center">
          <span className="login-eyebrow">🎓 Học có lộ trình</span>
          <h1>Học thông minh<br />cùng {TUTOR_NAME}</h1>
          <div className="lead">
            Đi theo mục lục chương trình, học từng đơn vị kiến thức với ví dụ minh hoạ,
            làm bài kiểm tra nhanh và hỏi trợ lý bất cứ khi nào chưa rõ.
          </div>
          <div className="login-feats">
            {FEATS.map((f, i) => (
              <div className="login-feat" key={i}><span className="fic" aria-hidden>{f.ic}</span> {f.t}</div>
            ))}
          </div>
        </div>
        <div className="login-hero-foot">Trợ lý trả lời bám sách giáo khoa — không có trong SGK thì báo, không bịa.</div>
      </aside>

      <main className="login-main">
        <div className="login-top">
          <button className="login-icon-btn" type="button" onClick={cycle} title={`Giao diện: ${label}`} aria-label="Đổi giao diện">{icon}</button>
        </div>
        <div className="login-mobilebrand">
          <div className="logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <b>{TUTOR_NAME}</b>
        </div>

        <div className="login-card">
          <div>
            <div className="login-hi">Xin chào! 👋</div>
            <div className="login-hi-sub">
              {mode === "login" ? `Đăng nhập để tiếp tục học cùng ${TUTOR_NAME}.` : "Tạo tài khoản để bắt đầu học."}
            </div>
          </div>

          <div className="login-tabs">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Đăng nhập</button>
            <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Đăng ký</button>
          </div>

          {error && <div className="login-err">⚠️ {error}</div>}

          <form className="login-form" onSubmit={submit}>
            {mode === "register" && (
              <>
                <label>Họ và tên
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nguyễn Minh An" required />
                </label>
                <div className="login-roles">
                  <div className="login-role-label">Bạn là ai?</div>
                  {ROLES.map((r) => (
                    <button key={r.value} type="button" className={"login-role" + (role === r.value ? " sel" : "")}
                      aria-pressed={role === r.value} onClick={() => setRole(r.value)}>
                      <span className="ric" aria-hidden>{r.icon}</span>
                      <span>
                        <span className="rname" style={{ display: "block" }}>{r.title}</span>
                        <span className="rdesc">{r.desc}</span>
                      </span>
                      <span className="rcheck" aria-hidden>✓</span>
                    </button>
                  ))}
                </div>
              </>
            )}
            <label>Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ten@email.com" required />
            </label>
            <label>Mật khẩu
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            </label>
            <button className="login-submit" type="submit" disabled={busy}>
              {busy ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}
            </button>
          </form>

          <div className="login-foot">
            {mode === "login" ? (
              <>Chưa có tài khoản?{" "}
                <button type="button" className="login-link" onClick={() => setMode("register")}>Đăng ký ngay</button>
              </>
            ) : (
              <>Đã có tài khoản?{" "}
                <button type="button" className="login-link" onClick={() => setMode("login")}>Đăng nhập</button>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
