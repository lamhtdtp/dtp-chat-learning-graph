import { useState } from "react";
import { ApiError, adminCreateUser } from "../api";

type VaiTro = (typeof VAI_TRO)[number]["v"];

const VAI_TRO = [
  { v: "chuyen_gia", label: "✍️ Chuyên gia", desc: "Chỉ biên soạn nội dung — không thấy phần quản trị" },
  { v: "giao_vien", label: "👩‍🏫 Giáo viên", desc: "Biên soạn + dạy trên app học (slide, hướng dẫn dạy)" },
  { v: "admin", label: "🛡️ Quản trị", desc: "Toàn quyền: quản lý tài khoản + nội dung" },
] as const;

const MK_TOI_THIEU = 8;   // khớp ràng buộc Field(min_length=8) phía server

/** Form tạo tài khoản chuyên gia / quản trị.
 *
 *  Học sinh KHÔNG tạo ở đây — các em tự đăng ký ở app học. Đây chỉ dành cho tài
 *  khoản nội bộ mà /auth/register cố tình không cho tự chọn vai trò. */
export function TaoTaiKhoan({ onDone }: { onDone: () => void }) {
  const [mo, setMo] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<VaiTro>("chuyen_gia");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const dong = () => { setMo(false); setErr(null); setOk(null); };
  const hopLe = email.trim() && name.trim() && password.length >= MK_TOI_THIEU;

  const gui = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!hopLe || busy) return;
    setBusy(true); setErr(null); setOk(null);
    try {
      const u = await adminCreateUser({ email: email.trim(), password, name: name.trim(), role });
      setOk(`Đã tạo ${u.email}`);
      // Giữ form mở + giữ vai trò để tạo tiếp nhiều tài khoản cùng loại.
      setEmail(""); setName(""); setPassword("");
      onDone();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Không kết nối được máy chủ");
    } finally { setBusy(false); }
  };

  if (!mo) {
    return (
      <button className="btn btn-primary" type="button" onClick={() => setMo(true)}>
        ＋ Tạo tài khoản
      </button>
    );
  }

  return (
    <>
      <div className="scrim" onClick={dong} />
      <aside className="drawer" role="dialog" aria-label="Tạo tài khoản">
        <div className="dw-h">
          <div style={{ flex: 1 }}>
            <div className="eyebrow">Tài khoản nội bộ</div>
            <h2>Tạo tài khoản</h2>
          </div>
          <button className="dw-close" type="button" onClick={dong} aria-label="Đóng">✕</button>
        </div>
        <form className="dw-body" onSubmit={gui}>
          {err && <div className="warn-box" style={{ marginBottom: 14 }}>⚠️ {err}</div>}
          {ok && <div className="sgk-box" style={{ marginBottom: 14 }}>✅ {ok}</div>}

          <div className="esec">
            <div className="esec-h"><span className="n">1</span> Vai trò</div>
            {VAI_TRO.map((r) => (
              <label className={"vt-o" + (role === r.v ? " on" : "")} key={r.v}>
                <input type="radio" name="role" value={r.v} checked={role === r.v}
                  onChange={() => setRole(r.v)} />
                <div><b>{r.label}</b><div className="vt-d">{r.desc}</div></div>
              </label>
            ))}
            <div className="badge-man" style={{ marginTop: 8 }}>
              Học sinh tự đăng ký ở app học — không tạo ở đây.
            </div>
          </div>

          <div className="esec">
            <div className="esec-h"><span className="n">2</span> Thông tin đăng nhập</div>
            <label className="lbl">Họ tên</label>
            <input type="text" value={name} placeholder="Nguyễn Văn A" required
              onChange={(e) => setName(e.target.value)} />
            <label className="lbl" style={{ marginTop: 10 }}>Email</label>
            <input type="email" value={email} placeholder="ten@truong.edu.vn" required
              onChange={(e) => setEmail(e.target.value)} />
            <label className="lbl" style={{ marginTop: 10 }}>
              Mật khẩu
              <span className="lbl-dem">{password.length}/{MK_TOI_THIEU}</span>
            </label>
            <input type="password" value={password} placeholder={`Tối thiểu ${MK_TOI_THIEU} ký tự`}
              required minLength={MK_TOI_THIEU} onChange={(e) => setPassword(e.target.value)} />
          </div>
        </form>
        <div className="dw-foot">
          <button className="btn btn-ghost" type="button" onClick={dong}>Đóng</button>
          <div style={{ flex: 1 }} />
          <button className="btn btn-primary" type="button" disabled={!hopLe || busy} onClick={gui}>
            {busy ? "Đang tạo…" : "Tạo tài khoản"}
          </button>
        </div>
      </aside>
    </>
  );
}
