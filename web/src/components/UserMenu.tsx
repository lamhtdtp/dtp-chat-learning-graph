import { useEffect, useRef, useState } from "react";

// Menu người dùng ở góc phải app-bar: hiện TÊN + vai trò, bấm mở dropdown có nút
// Đăng xuất. Thay cho avatar bấm-là-thoát-ngay (dễ bấm nhầm, không thấy tên).
const ROLE_LABEL: Record<string, string> = { hoc_sinh: "Học sinh", giao_vien: "Giáo viên", admin: "Quản trị" };

export function UserMenu({ name, role, onLogout }: { name: string; role?: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const initial = (name || "?").trim().charAt(0).toUpperCase();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div className="user-menu" ref={ref}>
      <button
        className="user-btn"
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={name}
      >
        <span className="user-avatar" aria-hidden>{initial}</span>
        <span className="user-name">{name || "Tài khoản"}</span>
        <span className="user-caret" aria-hidden>▾</span>
      </button>

      {open && (
        <div className="user-pop" role="menu">
          <div className="user-pop-head">
            <span className="user-avatar lg" aria-hidden>{initial}</span>
            <div className="user-pop-info">
              <div className="user-pop-name">{name || "Tài khoản"}</div>
              {role && <div className="user-pop-role">{ROLE_LABEL[role] ?? role}</div>}
            </div>
          </div>
          <button className="user-pop-item" role="menuitem" type="button" onClick={onLogout}>
            <span aria-hidden>⎋</span> Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
