import { useEffect, useState } from "react";
import {
  ApiError, adminListUsers, adminSetActive, adminSetSettings, adminUserMessages, tokenStore,
} from "../api";
import { TUTOR_NAME } from "../config";
import { Portal } from "./Portal";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import type { AdminMessage, AdminUser, Role } from "../types";

export function AdminView({ name, onLogout }: { name: string; onLogout: () => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [qUser, setQUser] = useState<AdminUser | null>(null);
  const [msgs, setMsgs] = useState<AdminMessage[] | null>(null);

  const handle = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return; }
    setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
  };
  const load = () => { setErr(null); adminListUsers().then(setUsers).catch(handle); };
  useEffect(() => { load(); }, []);

  const patch = async (fn: () => Promise<unknown>) => {
    try { await fn(); load(); } catch (e) { handle(e); }
  };
  const openQuestions = async (u: AdminUser) => {
    setQUser(u); setMsgs(null);
    try { setMsgs(await adminUserMessages(u.id)); } catch (e) { handle(e); }
  };

  return (
    <div className="hub" data-subject="toan">
      <div className="app-bar">
        <div className="brand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div className="brand-name">{TUTOR_NAME}</div>
        </div>
        <span className="pill-select" style={{ cursor: "default" }}>🛠️ Quản trị</span>
        <div className="spacer" />
        <ThemeToggle />
        <UserMenu name={name} role="admin" onLogout={onLogout} />
      </div>

      <div className="hub-body">
        <div className="hub-greet">Quản lý người dùng</div>
        <div className="hub-greet-sub">Theo dõi hoạt động, khoá/mở tài khoản, đổi vai trò &amp; hạn mức chat/ngày.</div>
        {err && <div className="exam-warn" style={{ marginTop: 12 }}>⚠️ {err}</div>}

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th>
                <th>Hạn mức/ngày</th><th className="num">Phiên</th><th className="num">Câu hỏi</th>
                <th className="num">Hôm nay</th><th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={u.is_active ? "" : "locked"}>
                  <td>
                    <div className="au-name">{u.name}</div>
                    <div className="au-email">{u.email}</div>
                  </td>
                  <td>
                    <select value={u.role} onChange={(e) => patch(() => adminSetSettings(u.id, { role: e.target.value as Role }))}>
                      <option value="hoc_sinh">Học sinh</option>
                      <option value="giao_vien">Giáo viên</option>
                      <option value="admin">Quản trị</option>
                    </select>
                  </td>
                  <td>
                    <button className={"au-pill " + (u.is_active ? "on" : "off")}
                      onClick={() => patch(() => adminSetActive(u.id, !u.is_active))} type="button">
                      {u.is_active ? "● Hoạt động" : "○ Đã khoá"}
                    </button>
                  </td>
                  <td>
                    <input className="au-limit" type="number" min={0} placeholder="mặc định"
                      defaultValue={u.daily_limit_override ?? ""}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if (v === (u.daily_limit_override?.toString() ?? "")) return;
                        patch(() => adminSetSettings(u.id, v === "" ? { clear_limit: true } : { daily_limit: Number(v) }));
                      }} />
                  </td>
                  <td className="num">{u.sessions}</td>
                  <td className="num">{u.questions}</td>
                  <td className="num">{u.today}</td>
                  <td><button className="btn" type="button" onClick={() => openQuestions(u)}>Câu hỏi</button></td>
                </tr>
              ))}
              {users.length === 0 && !err && (
                <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--ink-3)", padding: 24 }}>Đang tải…</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {qUser && (
        <Portal>
          <div className="modal-scrim" onClick={() => setQUser(null)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <div className="modal-head">
                <span>💬 Câu hỏi của {qUser.name}</span>
                <button className="modal-close" onClick={() => setQUser(null)} type="button" aria-label="Đóng">✕</button>
              </div>
              <div className="modal-body">
                {msgs === null ? <div className="book-msg">Đang tải…</div>
                  : msgs.length === 0 ? <div className="book-msg">Chưa có câu hỏi nào.</div>
                  : <ul className="admin-qs">
                      {msgs.map((m, i) => (
                        <li key={i}>
                          <div className="q-meta">{new Date(m.created_at).toLocaleString("vi-VN")} · {m.subject}</div>
                          <div className="q-text">{m.content}</div>
                        </li>
                      ))}
                    </ul>}
              </div>
            </div>
          </div>
        </Portal>
      )}
    </div>
  );
}
