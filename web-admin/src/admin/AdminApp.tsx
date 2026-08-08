import { useEffect, useState } from "react";
import { getMe, tokenStore } from "../api";
import { useTheme } from "../hooks/useTheme";
import { AdminLogin } from "./AdminLogin";
import { Dashboard } from "./Dashboard";
import type { Role } from "../types";

type Session = { name: string; role: Role } | null;

// Vai trò làm việc trong CMS. `chuyen_gia` chỉ thấy phần Nội dung (lọc ở
// Dashboard); `admin` thấy tất cả. Học sinh dùng app học, không vào đây.
const VAO_DUOC: Role[] = ["chuyen_gia", "giao_vien", "admin"];

// App QUẢN TRỊ riêng (phục vụ tại /admin). Chỉ tài khoản nội bộ vào được;
// vai trò khác đăng nhập sẽ bị từ chối ngay tại đây.
export function AdminApp() {
  useTheme();
  const [session, setSession] = useState<Session>(null);
  const [ready, setReady] = useState(false);

  const restore = () =>
    getMe()
      .then((u) => {
        if (VAO_DUOC.includes(u.role)) setSession({ name: u.name, role: u.role });
        else { tokenStore.clear(); setSession(null); }  // học sinh -> loại
      })
      .catch(() => tokenStore.clear());

  useEffect(() => {
    if (!tokenStore.get()) { setReady(true); return; }
    restore().finally(() => setReady(true));
  }, []);

  const logout = () => { tokenStore.clear(); setSession(null); };

  if (!ready) return null;
  if (!session) return <AdminLogin onAuthed={() => restore()} />;
  return <Dashboard name={session.name} role={session.role} onLogout={logout} />;
}
