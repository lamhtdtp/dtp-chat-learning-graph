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
  DmTrung,
  BookJob,
  DocThu,
  SoatSach,
  KhoSgk,
  MaTran,
  OnTap,
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
  // Route KHÔNG được proxy về API sẽ trả index.html của SPA với status 200:
  // `res.ok` là true, rồi `res.json()` nổ SyntaxError thô, caller chỉ thấy
  // "Không gọi được máy chủ" và không có gì để lần. Nói thẳng ra bệnh.
  const kieu = res.headers.get("content-type") ?? "";
  if (!kieu.includes("json")) {
    throw new ApiError(res.status,
      `Máy chủ trả ${kieu || "nội dung không phải JSON"} cho ${path} — `
      + "route này chưa được proxy về API (kiểm nginx / vite proxy).");
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

/** Upload ẢNH minh hoạ (multipart). Trả minh_hoa đã cập nhật. */
export async function cmsUploadAnh(topicId: number, file: File, caption = ""):
  Promise<{ minh_hoa: CmsMedia[] }> {
  const fd = new FormData();
  fd.append("file", file);
  const t = tokenStore.get();
  const res = await fetch(
    `${API_BASE}/cms/topics/${topicId}/anh?caption=${encodeURIComponent(caption)}`,
    { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd },
  );
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* mặc định */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

/** §2.4 — soát thư mục ảnh trang: đủ trang chưa, khuyết trang nào. */
export function cmsSoatSach(mon: string, khoi: string, tap: number): Promise<SoatSach> {
  return req(`/cms/sach/soat?mon=${mon}&khoi=${khoi}&tap=${tap}`, { auth: true });
}

/** Tải ảnh trang lên. Tệp không đoán chắc số trang sẽ vào danh sách chờ gán. */
export async function cmsNapTepSach(mon: string, khoi: string, tap: number, files: File[]):
  Promise<SoatSach> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/cms/sach/tep?mon=${mon}&khoi=${khoi}&tap=${tap}`,
    { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd });
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* mặc định */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

/** Gán số trang cho tệp đang chờ (so=null để bỏ tệp). */
export function cmsGanSoTrang(mon: string, khoi: string, tap: number,
                              ten: string, so: number | null): Promise<SoatSach> {
  return req(`/cms/sach/tep/gan?mon=${mon}&khoi=${khoi}&tap=${tap}`,
    { method: "POST", auth: true, body: { ten, so } });
}

/** Đọc thử vài trang — KHÔNG ghi kho. */
export function cmsDocThuSach(mon: string, khoi: string, tap: number,
                              trang: number[] = [], lam_lai = false): Promise<DocThu> {
  return req(`/cms/sach/doc-thu?mon=${mon}&khoi=${khoi}&tap=${tap}`,
    { method: "POST", auth: true, body: { trang, lam_lai } });
}

/** Nạp cả tập — tạo việc chạy nền. */
export function cmsNapSach(mon: string, khoi: string, tap: number, sach: string):
  Promise<BookJob> {
  return req("/cms/sach/nap", { method: "POST", auth: true,
    body: { mon, khoi, tap, sach } });
}

export function cmsJobSach(id: number): Promise<BookJob> {
  return req(`/cms/sach/jobs/${id}`, { auth: true });
}
export function cmsDsJobSach(): Promise<{ jobs: BookJob[] }> {
  return req("/cms/sach/jobs", { auth: true });
}
export function cmsLenhJobSach(id: number, lenh: "tam_dung" | "tiep" | "huy"): Promise<BookJob> {
  return req(`/cms/sach/jobs/${id}/lenh`, { method: "POST", auth: true, body: { lenh } });
}

/** Các đơn vị TRÙNG TÊN trong danh mục + đề xuất giữ bản nào. */
export function cmsDanhMucTrung(mon = "Toán", khoi = "Lớp 6"): Promise<DmTrung> {
  return req(`/cms/danh-muc/trung?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`,
    { auth: true });
}

/** Gộp các bản trùng về một đơn vị. */
export function cmsGopDonVi(giu: number, bo: number[]):
  Promise<{ giu: number; bo: number[]; da_doi: Record<string, number> }> {
  return req("/cms/danh-muc/gop", { method: "POST", auth: true, body: { giu, bo } });
}

/** Sinh hình cho MỘT ví dụ. Bỏ trống prompt -> dùng mô tả AI đã đề xuất. */
export function cmsSinhAnhViDu(topicId: number, chiSo: number, prompt = ""):
  Promise<{ chi_so: number; anh: string; anh_xem: string }> {
  return req(`/cms/topics/${topicId}/vi-du/${chiSo}/anh`,
    { method: "POST", auth: true, body: { prompt } });
}

/** Upload hình cho MỘT ví dụ (chuyên gia tự chụp/scan/vẽ). */
export async function cmsUploadAnhViDu(topicId: number, chiSo: number, file: File):
  Promise<{ chi_so: number; anh: string; anh_xem: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/cms/topics/${topicId}/anh?vi_du=${chiSo}`,
    { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd });
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* mặc định */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

/** Xem thử phạm vi một node ôn tập (dùng chung endpoint với app học sinh). */
export function cmsOnTap(pham_vi: string, gia_tri: string, mon = "Toán", khoi = "Lớp 6"):
  Promise<OnTap> {
  return req(`/on-tap?pham_vi=${pham_vi}&gia_tri=${encodeURIComponent(gia_tri)}`
    + `&mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
/** Nạp lại ma trận từ tệp .docx/.md — THAY toàn bộ ma trận của môn+lớp+kỳ. */
export async function cmsNapMaTran(file: File, mon: string, khoi: string, hoc_ky: string):
  Promise<{ so_dong: number; don_vi_moi: { topic_id: number; ten: string; mach: string }[] }> {
  const fd = new FormData();
  fd.append("file", file);
  const t = tokenStore.get();
  const q = `mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}&hoc_ky=${hoc_ky}`;
  const res = await fetch(`${API_BASE}/cms/ma-tran/nap?${q}`,
    { method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd });
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try { detail = (await res.json()).detail ?? detail; } catch { /* mặc định */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}
