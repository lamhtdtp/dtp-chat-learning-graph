import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError, adminListUsers, adminSetActive, adminSetSettings,
  cmsCatalog, cmsCurriculum, tokenStore,
} from "../api";
import type { CmsCatalog } from "../api";
import { useTheme } from "../hooks/useTheme";
import type { AdminUser, CmsGroup, CmsUnit, Role } from "../types";
import { DrawerEditor } from "./DrawerEditor";
import { HocTapChart } from "./HocTapChart";
import { KetQuaDrawer } from "./KetQuaDrawer";
import { TaoTaiKhoan } from "./TaoTaiKhoan";

type View = "overview" | "content" | "ingest" | "matrix" | "users" | "settings";
type Flat = CmsUnit & { mach: string };

// `chiAdmin`: nhóm chỉ quản trị thấy. Chuyên gia là vai trò CMS-only, chỉ được
// phần Nội dung — Ma trận / Người dùng / Cài đặt là việc quản trị.
const NAV: { group: string; chiAdmin?: boolean; items: { v: View; label: string; icon: string }[] }[] = [
  { group: "Nội dung", items: [
    { v: "overview", label: "Tổng quan", icon: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z" },
    { v: "content", label: "Chương trình & nội dung", icon: "M4 19.5A2.5 2.5 0 016.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" },
    { v: "ingest", label: "Nạp sách bằng AI", icon: "M12 3v12m0-12l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" },
  ] },
  { group: "Hệ thống", chiAdmin: true, items: [
    { v: "matrix", label: "Ma trận đặc tả", icon: "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18" },
    { v: "users", label: "Người dùng", icon: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8z" },
    { v: "settings", label: "Cài đặt", icon: "M12 15a3 3 0 100-6 3 3 0 000 6z" },
  ] },
];
const CRUMB: Record<View, [string, string]> = {
  overview: ["Nội dung", "Tổng quan"], content: ["Nội dung", "Chương trình & nội dung"],
  ingest: ["Nội dung", "Nạp sách bằng AI"], matrix: ["Hệ thống", "Ma trận đặc tả"],
  users: ["Hệ thống", "Người dùng"], settings: ["Hệ thống", "Cài đặt"],
};
const PILL: Record<string, [string, string]> = {
  published: ["p-xong", "Đã xuất bản"], review: ["p-duyet", "Chờ duyệt"],
  draft: ["p-nhap", "Nháp"], chua_bien_soan: ["p-nhap", "Chưa soạn"],
};
const ROLE_LABEL: Record<Role, string> = {
  hoc_sinh: "Học sinh", giao_vien: "Giáo viên", chuyen_gia: "Chuyên gia", admin: "Quản trị",
};

function Icon({ d }: { d: string }) {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={d} /></svg>;
}

export function Dashboard({ name, role, onLogout }: {
  name: string; role: Role; onLogout: () => void;
}) {
  const laAdmin = role === "admin";
  const nav = NAV.filter((sec) => laAdmin || !sec.chiAdmin);
  const { cycle } = useTheme();
  const [view, setView] = useState<View>("content");
  const [groups, setGroups] = useState<CmsGroup[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [catalog, setCatalog] = useState<CmsCatalog | null>(null);
  const [mon, setMon] = useState("Toán");
  const [khoi, setKhoi] = useState("Lớp 6");
  const [hocKy, setHocKy] = useState("all");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [drawer, setDrawer] = useState<{ topicId: number; mode: "edit" | "preview" } | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const toastT = useRef<number>();

  const toast = (m: string) => {
    setToastMsg(m); window.clearTimeout(toastT.current);
    toastT.current = window.setTimeout(() => setToastMsg(null), 2100);
  };
  const handle = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { tokenStore.clear(); onLogout(); return; }
    setErr(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
  };
  const loadCurriculum = () => cmsCurriculum(mon, khoi, hocKy).then(setGroups).catch(handle);
  const loadUsers = () => adminListUsers().then(setUsers).catch(handle);
  // /admin/users chỉ admin gọi được — chuyên gia gọi sẽ ăn 403 rồi hiện banner
  // lỗi đỏ ngay khi vừa vào, dù họ chẳng cần dữ liệu đó.
  useEffect(() => {
    if (laAdmin) loadUsers();
    cmsCatalog().then(setCatalog).catch(() => { /* bộ lọc phụ */ });
  }, []); // eslint-disable-line
  useEffect(() => { loadCurriculum(); }, [mon, khoi, hocKy]); // eslint-disable-line

  const flat: Flat[] = useMemo(() => groups.flatMap((g) => g.dv.map((d) => ({ ...d, mach: g.mach }))), [groups]);
  const kpi = useMemo(() => ({
    total: flat.length,
    published: flat.filter((u) => u.trang_thai === "published").length,
    review: flat.filter((u) => u.trang_thai === "review").length,
    ai: flat.filter((u) => u.ai).length,
  }), [flat]);

  const patchUser = async (fn: () => Promise<unknown>) => { try { await fn(); loadUsers(); } catch (e) { handle(e); } };

  return (
    <div className="admin">
      <aside className="sb">
        <div className="sb-brand"><div className="sb-logo"><img src="/dtp-logo.png" alt="DTP" /></div>
          <div><b>Gia sư DTP</b><span>Bảng quản trị</span></div></div>
        <nav className="sb-nav">
          {nav.map((sec) => (
            <div key={sec.group}>
              <div className="sb-group">{sec.group}</div>
              {sec.items.map((it) => (
                <button key={it.v} className={"sb-link" + (view === it.v ? " active" : "")} type="button"
                  onClick={() => setView(it.v)}>
                  <Icon d={it.icon} /> {it.label}
                  {it.v === "content" && <span className="ct">{flat.length}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sb-user">
          <div className="sb-ava">{(name || "?").trim().charAt(0).toUpperCase()}</div>
          <div><div className="nm">{name}</div><div className="rl">{ROLE_LABEL[role]}</div></div>
          <button className="sb-logout" type="button" title="Đăng xuất" onClick={onLogout}>⎋</button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="crumb">{CRUMB[view][0]} · <b>{CRUMB[view][1]}</b></div>
          <div className="search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input type="text" placeholder="Tìm đơn vị kiến thức…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <button className="tb-btn" type="button" title="Đổi giao diện" onClick={cycle} aria-label="Đổi giao diện">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v1M12 20v1M4.2 4.2l.7.7M19 19l.7.7M3 12h1M20 12h1M4.2 19.8l.7-.7M19 5l.7-.7M12 8a4 4 0 100 8 4 4 0 000-8z" /></svg>
          </button>
        </div>

        <div className="content">
          {err && <div className="warn-box" style={{ marginBottom: 16 }}>⚠️ {err}</div>}

          {(view === "overview" || view === "content") && (
            <>
              <div className="page-head">
                <div>
                  <h1>{view === "overview" ? "Tổng quan" : "Chương trình & nội dung"}</h1>
                  <div className="ps">{view === "overview"
                    ? "Tình hình biên soạn nội dung Toán 6"
                    : "Biên soạn nội dung 4 phần theo Mạch → Đơn vị kiến thức"}</div>
                </div>
                <div className="sp" />
                {/* Bỏ CTA "Nạp bằng AI": mục đó đang là màn hình "Đang phát triển",
                    nút chính dẫn vào ngõ cụt còn tệ hơn không có nút. */}
              </div>

              {/* Tổng quan = hai lớp: học sinh học đến đâu, rồi mới tới tình hình
                  biên soạn. Trang này trước chỉ có lớp thứ hai. */}
              {view === "overview" && <HocTapChart />}

              <div className="kpis">
                <Kpi ic="ic-total" v={kpi.total} l="Đơn vị kiến thức" />
                <Kpi ic="ic-ok" v={kpi.published} l="Đã xuất bản" trend={kpi.total ? Math.round(kpi.published / kpi.total * 100) + "%" : undefined} />
                <Kpi ic="ic-warn" v={kpi.review} l="Chờ duyệt" />
                <Kpi ic="ic-ai" v={kpi.ai} l="Có nội dung AI" />
              </div>
            </>
          )}

          {view === "content" && (
            <div className="catalog-bar">
              <label>Lớp
                <select value={khoi} onChange={(e) => setKhoi(e.target.value)}>
                  {(catalog?.grades ?? [khoi]).map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </label>
              <label>Môn học
                <select value={mon} onChange={(e) => setMon(e.target.value)}>
                  {(catalog?.subjects ?? [mon]).map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label>Học kỳ
                <select value={hocKy} onChange={(e) => setHocKy(e.target.value)}>
                  {(catalog?.semesters ?? [{ value: "all", label: "Cả năm" }]).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </label>
            </div>
          )}

          {view === "content" && (
            <div className="panel">
              <div className="panel-h">
                <h3>Đơn vị kiến thức</h3><div className="sp" />
                <div className="filters">
                  {[["all", "Tất cả"], ["draft", "Nháp"], ["review", "Chờ duyệt"], ["published", "Đã xuất bản"]].map(([v, l]) => (
                    <button key={v} className={"fbtn" + (filter === v ? " on" : "")} type="button" onClick={() => setFilter(v)}>{l}</button>
                  ))}
                </div>
              </div>
              <ContentTable flat={flat} filter={filter} search={search}
                onEdit={(id) => setDrawer({ topicId: id, mode: "edit" })}
                onPreview={(id) => setDrawer({ topicId: id, mode: "preview" })} />
            </div>
          )}

          {view === "overview" && (
            <div className="panel"><div className="panel-h"><h3>Tiến độ hoàn thiện nội dung</h3></div>
              <div style={{ padding: 18 }}>
                <OverviewBar flat={flat} />
                <div style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 10 }}>
                  Trung bình 4 phần (Khái niệm · Minh họa · Ví dụ · Kiểm tra) trên toàn bộ đơn vị.
                </div>
              </div>
            </div>
          )}

          {view === "users" && <UsersView users={users} search={search} onPatch={patchUser} onCreated={loadUsers} />}
          {view === "ingest" && <Stub icon="🤖" ten="Nạp sách bằng AI" />}
          {view === "matrix" && <Stub icon="🧩" ten="Ma trận đặc tả" />}
          {view === "settings" && <Stub icon="⚙️" ten="Cài đặt" />}
        </div>
      </div>

      {drawer && (
        <DrawerEditor topicId={drawer.topicId} initMode={drawer.mode}
          onClose={() => setDrawer(null)} onSaved={loadCurriculum} toast={toast} />
      )}
      {toastMsg && <div className="toast">{toastMsg}</div>}
    </div>
  );
}

function Kpi({ ic, v, l, trend }: { ic: string; v: number; l: string; trend?: string }) {
  return (
    <div className="kpi">
      <div className={"ic " + ic}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5z" /></svg>
      </div>
      {trend && <span className="trend">▲ {trend}</span>}
      <div className="v tnum">{v}</div><div className="l">{l}</div>
    </div>
  );
}

function OverviewBar({ flat }: { flat: Flat[] }) {
  const avg = flat.length ? Math.round(flat.reduce((a, u) => a + u.completeness.done, 0) / flat.length / 4 * 100) : 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div className="cbar" style={{ flex: 1 }}><div className="tk" style={{ width: "100%", height: 10 }}><i style={{ width: `${avg}%` }} /></div></div>
      <b className="tnum" style={{ fontSize: 20, fontFamily: "var(--disp)" }}>{avg}%</b>
    </div>
  );
}

const PAGE_SIZE = 10;

/** Cắt trang cho 1 danh sách đã lọc. `resetKey` đổi -> về trang 1 (đổi bộ lọc mà
 *  vẫn ở trang 7 thì thấy bảng rỗng). Gộp ở đây vì hai bảng dùng y hệt nhau. */
function usePaging<T>(rows: T[], resetKey: unknown) {
  const [page, setPage] = useState(1);
  useEffect(() => { setPage(1); }, [resetKey]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageSafe = Math.min(page, pages);
  return {
    pages, page: pageSafe, setPage,
    shown: rows.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE),
  };
}

/** Dãy số trang có rút gọn: luôn giữ trang đầu/cuối, trang hiện tại và 1 trang
 *  kề hai bên; khoảng cách còn lại thay bằng "…". Ví dụ 12 trang, đang ở 7:
 *  1 … 6 7 8 … 12 — bấm được tới đích thay vì phải Next nhiều lần. */
function daySoTrang(page: number, pages: number): (number | "…")[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const quanh = [page - 1, page, page + 1].filter((p) => p > 1 && p < pages);
  const out: (number | "…")[] = [1];
  if (quanh[0] > 2) out.push("…");
  out.push(...quanh);
  if (quanh[quanh.length - 1] < pages - 1) out.push("…");
  out.push(pages);
  return out;
}

function Pager({ page, pages, total, onPage }: {
  page: number; pages: number; total: number; onPage: (p: number) => void;
}) {
  if (total === 0) return null;
  const dau = (page - 1) * PAGE_SIZE + 1;
  const cuoi = Math.min(page * PAGE_SIZE, total);
  return (
    <nav className="pager" aria-label="Phân trang">
      {/* Vị trí hiện tại hiện cả khi chỉ có 1 trang — "47 mục" là thông tin có
          ích, còn nút bấm thì không cần khi không có gì để chuyển. */}
      <span className="pager-info">
        <b className="tnum">{dau}–{cuoi}</b> trong <b className="tnum">{total}</b>
      </span>
      {pages > 1 && (
        <div className="pager-ctl">
          <button className="pg-nav" type="button" disabled={page <= 1}
            onClick={() => onPage(page - 1)} aria-label="Trang trước">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          {daySoTrang(page, pages).map((p, i) => p === "…"
            ? <span className="pg-gap" key={`gap${i}`} aria-hidden>…</span>
            : <button className={"pg-num" + (p === page ? " on" : "")} key={p} type="button"
                aria-current={p === page ? "page" : undefined}
                aria-label={`Trang ${p}`} onClick={() => onPage(p)}>{p}</button>)}
          <button className="pg-nav" type="button" disabled={page >= pages}
            onClick={() => onPage(page + 1)} aria-label="Trang sau">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        </div>
      )}
    </nav>
  );
}

function ContentTable({ flat, filter, search, onEdit, onPreview }: {
  flat: Flat[]; filter: string; search: string; onEdit: (id: number) => void; onPreview: (id: number) => void;
}) {
  const q = search.trim().toLowerCase();
  const rows = flat.filter((u) => (filter === "all" || u.trang_thai === filter) && (!q || u.ten.toLowerCase().includes(q)));
  const { page, pages, setPage, shown } = usePaging(rows, `${filter}|${search}|${flat.length}`);
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>Đơn vị kiến thức</th><th>Nguồn</th><th>Hoàn thành</th><th>Trạng thái</th><th></th></tr></thead>
        <tbody>
          {shown.map((u) => {
            const [cls, label] = PILL[u.trang_thai] ?? PILL.chua_bien_soan;
            const pct = Math.round(u.completeness.done / u.completeness.total * 100);
            return (
              <tr key={u.topic_id}>
                <td><div className="u-name">{u.ten}</div><div className="u-mach">{u.mach}</div></td>
                <td>{u.ai
                  ? <span className="badge-ai">✨ AI</span>
                  : u.trang_thai === "chua_bien_soan" ? <span className="badge-man">—</span> : <span className="badge-man">Thủ công</span>}</td>
                <td><div className="cbar"><div className="tk"><i style={{ width: `${pct}%` }} /></div><span className="fr tnum">{u.completeness.done}/4</span></div></td>
                <td><span className={"pill " + cls}>{label}</span></td>
                <td><div className="row-act">
                  <button className="act edit" type="button" onClick={() => onEdit(u.topic_id)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></svg> Sửa
                  </button>
                  <button className="act" type="button" title="Xem trước" onClick={() => onPreview(u.topic_id)}>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></svg>
                  </button>
                </div></td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--ink-3)", padding: 28 }}>Không có đơn vị khớp bộ lọc.</td></tr>}
        </tbody>
      </table>
      <Pager page={page} pages={pages} total={rows.length} onPage={setPage} />
    </div>
  );
}


/** Màn hình chưa mở — dùng chung cho mọi mục đang phát triển, để ba chỗ không
 *  trôi mỗi nơi một kiểu. */
function Stub({ icon, ten }: { icon: string; ten: string }) {
  return (
    <div className="stub"><div>
      <div className="em">{icon}</div>
      <b style={{ fontSize: 18, color: "var(--ink)" }}>{ten}</b>
      <div style={{ marginTop: 6 }}>Đang phát triển.</div>
    </div></div>
  );
}

function UsersView({ users, search, onPatch, onCreated }: {
  users: AdminUser[]; search: string;
  onPatch: (fn: () => Promise<unknown>) => void;
  /** Tải lại danh sách sau khi tạo tài khoản mới. */
  onCreated: () => void;
}) {
  const q = search.trim().toLowerCase();
  const rows = users.filter((u) => !q || (u.name + " " + u.email).toLowerCase().includes(q));
  const { page, pages, setPage, shown } = usePaging(rows, `${search}|${users.length}`);
  const [xemKq, setXemKq] = useState<number | null>(null);
  return (
    <>
      <div className="page-head">
        <div><h1>Người dùng</h1><div className="ps">Quản lý tài khoản + theo dõi tiến độ học ({rows.length})</div></div>
        <div className="sp" />
        <TaoTaiKhoan onDone={onCreated} />
      </div>
      <div className="panel">
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th><th>Hạn mức/ngày</th><th className="tnum">Đạt</th><th className="tnum">Đang</th><th></th></tr></thead>
            <tbody>
              {shown.map((u) => (
                <tr key={u.id}>
                  <td><div className="u-name">{u.name}</div><div className="u-email">{u.email}</div></td>
                  <td>
                    <select className="au-role" value={u.role} onChange={(e) => onPatch(() => adminSetSettings(u.id, { role: e.target.value as Role }))}>
                      {(["hoc_sinh", "giao_vien", "chuyen_gia", "admin"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </select>
                  </td>
                  <td><button className={"au-pill " + (u.is_active ? "on" : "off")} type="button"
                    onClick={() => onPatch(() => adminSetActive(u.id, !u.is_active))}>{u.is_active ? "● Hoạt động" : "○ Đã khoá"}</button></td>
                  <td><input className="au-limit" type="number" min={0} placeholder="mặc định" defaultValue={u.daily_limit_override ?? ""}
                    onBlur={(e) => { const v = e.target.value.trim(); if (v === (u.daily_limit_override?.toString() ?? "")) return;
                      onPatch(() => adminSetSettings(u.id, v === "" ? { clear_limit: true } : { daily_limit: Number(v) })); }} /></td>
                  <td className="tnum">{u.hoan_thanh}</td>
                  <td className="tnum">{u.dang_hoc}</td>
                  <td><div className="row-act">
                    {/* Chỉ học sinh mới có kết quả học tập — GV/QT tài khoản không
                        sinh dữ liệu đánh giá, hiện nút ở đó chỉ dẫn tới bảng rỗng. */}
                    {u.role === "hoc_sinh" && (
                      <button className="act txt" type="button" title="Xem kết quả kiểm tra nhanh"
                        onClick={() => setXemKq(u.id)}>📊 Kết quả</button>
                    )}
                  </div></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-3)", padding: 24 }}>Không có người dùng khớp.</td></tr>}
            </tbody>
          </table>
        </div>
        <Pager page={page} pages={pages} total={rows.length} onPage={setPage} />
      </div>
      {xemKq != null && <KetQuaDrawer userId={xemKq} onClose={() => setXemKq(null)} />}
    </>
  );
}
