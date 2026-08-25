import { useState, type FormEvent } from "react";
import { ApiError, getMe, login, tokenStore } from "../api";
import { VAO_DUOC } from "./vaoDuoc";

// Đăng nhập cho khu quản trị: đăng nhập xong đối chiếu vai trò với VAO_DUOC —
// dùng chung danh sách với AdminApp, không chốt cứng "admin" ở đây nữa.
export function AdminLogin({ onAuthed }: { onAuthed: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await login(email.trim(), password);
      const me = await getMe();
      if (!VAO_DUOC.includes(me.role)) {
        tokenStore.clear();
        setErr("Tài khoản này không có quyền vào khu quản trị.");
        return;
      }
      onAuthed();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Không kết nối được máy chủ");
    } finally { setBusy(false); }
  };

  return (
    <div className="adm-login" data-subject="toan">
      <form className="adm-login-card" onSubmit={submit}>
        <div className="adm-login-brand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div>
            <div className="adm-login-title">Gia sư DTP</div>
            <div className="adm-login-sub">Khu quản trị</div>
          </div>
        </div>
        {err && <div className="adm-login-err">{err}</div>}
        <label className="adm-field">Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@dtp.vn" autoComplete="username" required />
        </label>
        <label className="adm-field">Mật khẩu
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password" required />
        </label>
        <button className="btn accent" type="submit" disabled={busy}>
          {busy ? "Đang đăng nhập…" : "Đăng nhập quản trị"}
        </button>
      </form>
    </div>
  );
}
