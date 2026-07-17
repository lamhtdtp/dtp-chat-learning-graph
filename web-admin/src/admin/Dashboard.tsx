import { useEffect, useMemo, useState } from "react";
import {
  ApiError, adminDailyStats, adminListUsers, adminSetActive, adminSetSettings,
  adminUserMessages, tokenStore,
} from "../api";
import { TUTOR_NAME } from "../config";
import { Portal } from "../components/Portal";
import { ThemeToggle } from "../components/ThemeToggle";
import { UserMenu } from "../components/UserMenu";
import type { AdminMessage, AdminUser, DailyStat, Role } from "../types";

type View = "overview" | "users";
type RoleFilter = "all" | Role;
const CHART_DAYS = 14;
const PAGE_SIZE = 12;

const ROLE_LABEL: Record<Role, string> = {
  hoc_sinh: "Học sinh", giao_vien: "Giáo viên", admin: "Quản trị",
};
const ROLE_FILTERS: RoleFilter[] = ["all", "hoc_sinh", "giao_vien", "admin"];

// Khu quản trị — DÙNG CHUNG shell với web (app-bar + tab + token màu). Trọng tâm:
// quản lý người dùng (học sinh & giáo viên) dùng hệ thống.
export function Dashboard({ name, onLogout }: { name: string; onLogout: () => void }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>("overview");
  const [qUser, setQUser] = useState<AdminUser | null>(null);
  const [msgs, setMsgs] = useState<AdminMessage[] | null>(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [page, setPage] = useState(1);

  const handle = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return; }
    setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
  };
  const load = () => {
    setErr(null);
    adminListUsers().then(setUsers).catch(handle);
    adminDailyStats(CHART_DAYS).then(setDaily).catch(() => { /* biểu đồ phụ, bỏ qua lỗi */ });
  };
  useEffect(() => { load(); }, []);

  const countByRole = (r: RoleFilter) =>
    r === "all" ? users.length : users.filter((u) => u.role === r).length;

  // Lọc theo vai trò + tìm kiếm (tên/email); phân trang phía client (số user nhỏ).
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) =>
      (roleFilter === "all" || u.role === roleFilter) &&
      (!q || (u.name + " " + u.email).toLowerCase().includes(q)));
  }, [users, search, roleFilter]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pages);
  const rows = filtered.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);
  useEffect(() => { setPage(1); }, [search, roleFilter]);

  const patch = async (fn: () => Promise<unknown>) => {
    try { await fn(); load(); } catch (e) { handle(e); }
  };
  const openQuestions = async (u: AdminUser) => {
    setQUser(u); setMsgs(null);
    try { setMsgs(await adminUserMessages(u.id)); } catch (e) { handle(e); }
  };

  const stats = useMemo(() => ({
    total: users.length,
    hoc_sinh: users.filter((u) => u.role === "hoc_sinh").length,
    giao_vien: users.filter((u) => u.role === "giao_vien").length,
    locked: users.filter((u) => !u.is_active).length,
    today: users.reduce((s, u) => s + u.today, 0),
    questions: users.reduce((s, u) => s + u.questions, 0),
  }), [users]);

  return (
    <div className="admin-page" data-subject="toan">
      <div className="app-bar">
        <div className="brand">
          <div className="dtp-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div className="brand-name">{TUTOR_NAME}</div>
          <span className="adm-badge">Quản trị</span>
        </div>
        <div className="spacer" />
        <ThemeToggle />
        <UserMenu name={name} role="admin" onLogout={onLogout} />
      </div>

      <div className="subject-switcher" role="tablist" aria-label="Khu quản trị">
        <button role="tab" aria-current={view === "overview" ? "true" : undefined}
          className="subject-tab" onClick={() => setView("overview")} type="button">
          <span aria-hidden>▦</span> Tổng quan
        </button>
        <button role="tab" aria-current={view === "users" ? "true" : undefined}
          className="subject-tab" onClick={() => setView("users")} type="button">
          <span aria-hidden>◔</span> Người dùng
        </button>
      </div>

      <div className="adm-wrap">
        {err && <div className="exam-warn" style={{ marginBottom: 16 }}>⚠️ {err}</div>}

        {view === "overview" && (
          <>
            <div className="adm-cards">
              <Card label="Tổng người dùng" value={stats.total} />
              <Card label="Học sinh" value={stats.hoc_sinh} accent="brand" />
              <Card label="Giáo viên" value={stats.giao_vien} accent="user" />
              <Card label="Bị khoá" value={stats.locked} accent={stats.locked ? "err" : undefined} />
              <Card label="Lượt hỏi hôm nay" value={stats.today} accent="data" />
              <Card label="Tổng câu hỏi" value={stats.questions} accent="data" />
            </div>
            <div className="adm-panel">
              <div className="adm-panel-h">Lượt hỏi theo ngày · {CHART_DAYS} ngày gần nhất</div>
              <DailyChart data={fillDays(daily, CHART_DAYS)} />
            </div>
          </>
        )}

        {view === "users" && (
          <>
            <div className="adm-toolbar">
              <input className="adm-search" type="search" value={search}
                onChange={(e) => setSearch(e.target.value)} placeholder="Tìm theo tên hoặc email…" />
              <div className="adm-filters" role="group" aria-label="Lọc theo vai trò">
                {ROLE_FILTERS.map((r) => (
                  <button key={r} type="button"
                    className={"adm-chip" + (roleFilter === r ? " on" : "")}
                    onClick={() => setRoleFilter(r)}>
                    {r === "all" ? "Tất cả" : ROLE_LABEL[r]}
                    <span className="adm-chip-n">{countByRole(r)}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th><th>Hạn mức/ngày</th>
                    <th className="num">Phiên</th><th className="num">Câu hỏi</th><th className="num">Hôm nay</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((u) => (
                    <tr key={u.id} className={u.is_active ? "" : "locked"}>
                      <td>
                        <div className="au-cell">
                          <span className="au-avatar" aria-hidden>{(u.name || "?").trim().charAt(0).toUpperCase()}</span>
                          <div>
                            <div className="au-name">{u.name}</div>
                            <div className="au-email">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <select className="au-role" value={u.role}
                          onChange={(e) => patch(() => adminSetSettings(u.id, { role: e.target.value as Role }))}>
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
                  {rows.length === 0 && (
                    <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--ink-3)", padding: 24 }}>
                      {users.length === 0 && !err ? "Đang tải…" : "Không có người dùng khớp."}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <div className="adm-pager">
                <button className="btn" type="button" disabled={pageSafe <= 1} onClick={() => setPage(pageSafe - 1)}>← Trước</button>
                <span>Trang {pageSafe}/{pages}</span>
                <button className="btn" type="button" disabled={pageSafe >= pages} onClick={() => setPage(pageSafe + 1)}>Sau →</button>
              </div>
            )}
          </>
        )}
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

function Card({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className={"adm-card" + (accent ? ` a-${accent}` : "")}>
      <div className="adm-card-v">{value}</div>
      <div className="adm-card-l">{label}</div>
    </div>
  );
}

// Bù các ngày trống = 0 -> chuỗi liên tục `days` ngày gần nhất (cũ -> mới).
function fillDays(daily: DailyStat[], days: number): DailyStat[] {
  const map = new Map(daily.map((d) => [d.date, d.count]));
  const now = new Date();
  const out: DailyStat[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push({ date: key, count: map.get(key) ?? 0 });
  }
  return out;
}

// Biểu đồ cột lượt hỏi/ngày — SVG tự vẽ (không thêm thư viện), theo token màu.
function DailyChart({ data }: { data: DailyStat[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const step = 44, baseY = 108, barW = 26, top = 14;
  const w = data.length * step;
  return (
    <svg className="adm-chart" viewBox={`0 0 ${w} 132`} width="100%" role="img"
      aria-label="Biểu đồ lượt hỏi theo ngày" preserveAspectRatio="xMidYMid meet">
      {data.map((d, i) => {
        const h = Math.max(2, Math.round((d.count / max) * (baseY - top)));
        const x = i * step + (step - barW) / 2;
        return (
          <g key={d.date}>
            <title>{`${d.count} lượt · ${d.date}`}</title>
            <rect x={x} y={baseY - h} width={barW} height={h} rx="4"
              fill={d.count ? "var(--brand)" : "var(--border-strong)"} />
            {d.count > 0 && (
              <text x={x + barW / 2} y={baseY - h - 4} textAnchor="middle"
                fontSize="10.5" fill="var(--ink-2)">{d.count}</text>
            )}
            <text x={x + barW / 2} y={baseY + 16} textAnchor="middle"
              fontSize="10.5" fill="var(--ink-3)">{d.date.slice(8, 10)}/{d.date.slice(5, 7)}</text>
          </g>
        );
      })}
    </svg>
  );
}
