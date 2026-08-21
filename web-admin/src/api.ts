import { API_BASE } from "./config";
import type {
  AdminOverview,
  AdminUser,
  AuthResult,
  CmsAiDraft,
  CmsGroup,
  CmsMedia,
  CmsPhan,
  CmsTongQuan,
  DmHocKy,
  KhoSgk,
  MaTran,
  CmsTopic,
  CmsViDu,
  CmsDay,
  CmsNhac,
  CmsQuiz,
  KetQuaHocSinh,
  Role,
} from "./types";

const TOKEN_KEY = "chat_learning_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth) {
    const t = tokenStore.get();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* giữ detail mặc định */
    }
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

async function post<T>(path: string, body: unknown, auth = false): Promise<T> {
  return req<T>(path, { body, auth });
}

// ── Xác thực (admin tạo bằng CLI; đây chỉ đăng nhập) ──
export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await post<AuthResult>("/auth/login", { email, password });
  tokenStore.set(res.token);
  return res;
}

export function getMe(): Promise<{ id: number; email: string; name: string; role: Role }> {
  return req("/auth/me", { auth: true });
}

// ── Admin ──
export function adminListUsers(): Promise<AdminUser[]> {
  return req("/admin/users", { auth: true });
}
export function adminSetActive(id: number, active: boolean): Promise<{ is_active: boolean }> {
  return req(`/admin/users/${id}/active`, { auth: true, body: { active } });
}
export function adminSetSettings(
  id: number, patch: { role?: Role; daily_limit?: number | null; clear_limit?: boolean },
): Promise<{ role: Role; daily_limit_override: number | null }> {
  return req(`/admin/users/${id}/settings`, { auth: true, body: patch });
}

// ── CMS chuyên gia biên soạn giáo trình (P4) ──
export interface CmsCatalog {
  grades: string[];
  subjects: string[];
  semesters: { value: string; label: string }[];
}
export function cmsCatalog(): Promise<CmsCatalog> {
  return req("/cms/catalog", { auth: true });
}
export function cmsCurriculum(mon = "Toán", khoi = "Lớp 6", hocKy = "all"): Promise<CmsGroup[]> {
  const hk = hocKy && hocKy !== "all" ? `&hoc_ky=${encodeURIComponent(hocKy)}` : "";
  return req(`/cms/curriculum?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}${hk}`, { auth: true });
}
export function cmsGetTopic(topicId: number): Promise<CmsTopic> {
  return req(`/cms/topics/${topicId}`, { auth: true });
}
export function cmsSaveTopic(topicId: number, body: {
  khai_niem: string; minh_hoa: CmsMedia[]; vi_du: CmsViDu[];
  day: CmsDay | null; nguon: string | null; trang_thai: string;
  khoi_dong?: string; hoat_dong?: string; luyen_tap?: string; bai_tap?: string;
  /** Bỏ trống = giữ nguyên cờ "AI soạn" đang có. */
  ai_soan?: boolean;
}): Promise<{ topic_id: number; trang_thai: string; completeness: CmsTopic["completeness"] }> {
  return req(`/cms/topics/${topicId}`, { method: "PUT", auth: true, body });
}
/** Giới hạn ô nhập CMS (đọc từ server — override được bằng env). */
export function cmsLimits(): Promise<{ nguon_max_chars: number }> {
  return req("/cms/limits", { auth: true });
}
/** Nháp AI bám SGK. `media=false` để chỉ soạn chữ (không tốn lần gọi sinh ảnh). */
export function cmsAiIngest(topicId: number, nguon = "", media = true): Promise<CmsAiDraft> {
  return req(`/cms/topics/${topicId}/ai-ingest`, { auth: true, body: { nguon, media } });
}
export function cmsGenerateQuiz(topicId: number): Promise<{ topic_id: number; quiz: CmsQuiz[]; so_cau: number }> {
  return req(`/cms/topics/${topicId}/quiz/generate`, { auth: true, body: {} });
}
/** Sinh lời nhắc chủ động (trợ lý hỏi lại sau khi HS đọc xong khái niệm).
 *  Sinh MỘT LẦN ở đây rồi cache — lúc HS đọc bài không gọi LLM, không trừ lượt hỏi. */
export function cmsGenerateNhac(topicId: number): Promise<{ topic_id: number; nhac: CmsNhac[] }> {
  return req(`/cms/topics/${topicId}/nhac/generate`, { auth: true, body: {} });
}
// Upload video: multipart -> không dùng req() (JSON). Trả minh_hoa đã cập nhật.
export async function cmsUploadVideo(topicId: number, file: File, caption = ""): Promise<{ minh_hoa: CmsMedia[] }> {
  const fd = new FormData();
  fd.append("file", file);
  const t = tokenStore.get();
  const res = await fetch(
    `${API_BASE}/cms/topics/${topicId}/video?caption=${encodeURIComponent(caption)}`,
    { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd },
  );
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* mặc định */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export { ApiError };

/** Kết quả làm Kiểm tra nhanh của 1 học sinh (giáo viên + quản trị). */
export function adminKetQua(userId: number): Promise<KetQuaHocSinh> {
  return req(`/admin/users/${userId}/result`, { auth: true });
}

/** Tạo tài khoản chuyên gia (giáo viên) hoặc quản trị. Chỉ quản trị gọi được. */
export function adminCreateUser(body: {
  email: string; password: string; name: string;
  role: "chuyen_gia" | "giao_vien" | "admin";   // học sinh tự đăng ký ở app học
}): Promise<{ id: number; email: string; name: string; role: Role }> {
  return req("/admin/users", { auth: true, body });
}

/** Số liệu học tập cho trang Tổng quan (giáo viên/chuyên gia/quản trị). */
export function adminOverview(ngay = 14): Promise<AdminOverview> {
  return req(`/admin/overview?ngay=${ngay}`, { auth: true });
}

/** Số liệu trang Tổng quan chuyên gia. */
export function cmsTongQuan(mon = "Toán", khoi = "Lớp 6"): Promise<CmsTongQuan> {
  return req(`/cms/tong-quan?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}

/** Lưu thứ tự + ẩn/hiện 7 phần. Tách khỏi PUT /topics/{id} để đổi thứ tự không
 *  ghi đè nội dung đang sửa dở. */
export function cmsLuuBoCuc(topicId: number, bo_cuc: { id: string; an: boolean }[]):
  Promise<{ topic_id: number; bo_cuc: CmsPhan[] }> {
  return req(`/cms/topics/${topicId}/bo-cuc`, { method: "PUT", auth: true, body: { bo_cuc } });
}
/** AI soạn gợi ý cho ĐÚNG một phần (không sinh cả bài). */
export function cmsAiPhan(topicId: number, phan: string):
  Promise<{ topic_id: number; phan: string; html: string }> {
  return req(`/cms/topics/${topicId}/phan/${phan}/ai`, { auth: true, body: {} });
}

export function cmsDanhMuc(mon = "Toán", khoi = "Lớp 6"): Promise<{ hoc_ky: DmHocKy[] }> {
  return req(`/cms/danh-muc?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
export function cmsKhoSgk(): Promise<KhoSgk> {
  return req("/cms/kho-sgk", { auth: true });
}
export function cmsMaTran(mon = "Toán", khoi = "Lớp 6"): Promise<MaTran> {
  return req(`/cms/ma-tran?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
