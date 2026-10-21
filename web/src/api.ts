import { API_BASE } from "./config";
import type {
  CurriculumGroup,
  BaiMa,
  CheDoNhapMa,
  DeCuoiKy,
  DeCuoiKyTomTat,
  DeLuyenThem,
  DeOnTap,
  KetQuaCuoiKy,
  KetQuaLuyenThem,
  OnTap,
  Lesson,
  MyStats,
  ProgressMe,
  AuthResult,
  Me,
  Neo,
  PhamVi,
  QuizResult,
  ThoiGianHoc,
  TutorAnswer,
  YcdMach,
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
  // `res.ok` là true, rồi `res.json()` nổ SyntaxError thô nên người dùng chỉ
  // thấy "không tải được" mà không có gì để lần. Nói thẳng ra bệnh.
  const kieu = res.headers.get("content-type") ?? "";
  if (res.status !== 204 && !kieu.includes("json")) {
    throw new ApiError(res.status,
      `Máy chủ trả ${kieu || "nội dung không phải JSON"} cho ${path} — `
      + "route này chưa được proxy về API (kiểm nginx / vite proxy).");
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

async function post<T>(path: string, body: unknown, auth = false): Promise<T> {
  return req<T>(path, { body, auth });
}

// ── Xác thực ──
export async function register(
  email: string,
  password: string,
  name: string,
): Promise<AuthResult> {
  // Không gửi `role`: tự đăng ký chỉ tạo học sinh (US-26), tài khoản giáo viên do admin cấp.
  const res = await post<AuthResult>("/auth/register", { email, password, name });
  tokenStore.set(res.token);
  return res;
}

export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await post<AuthResult>("/auth/login", { email, password });
  tokenStore.set(res.token);
  return res;
}

/** Hồ sơ người đang đăng nhập. Đăng nhập chỉ trả name+role — email nằm ở đây. */
export function getMe(): Promise<Me> {
  return req("/auth/me", { auth: true });
}

/** Kết quả xin phiếu SSO Testbank cho màn /sso/testbank. `veTestbank` chỉ có khi máy chủ ĐÃ chấp nhận
 *  `quay_ve` (địa chỉ do máy chủ dựng từ cấu hình) — không bao giờ lấy từ query của trang. */
export type KetQuaSsoTestbank =
  | { loai: "chuyen"; url: string }
  | { loai: "dang_nhap"; veTestbank: string }
  | { loai: "loi"; status: number; message: string; veTestbank: string | null };

export async function xinSsoTestbank(quayVe: string | null): Promise<KetQuaSsoTestbank> {
  const res = await fetch(`${API_BASE}/auth/sso/testbank`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenStore.get() ?? ""}` },
    body: JSON.stringify(quayVe === null ? {} : { quay_ve: quayVe }),
  }).catch(() => null);
  if (!res) return { loai: "loi", status: 0, message: "Không kết nối được máy chủ", veTestbank: null };
  let data: { detail?: string; che_do?: string; url?: string } = {};
  try { data = await res.json(); } catch { /* không phải JSON: rơi xuống nhánh lỗi */ }
  if (res.ok && data.url) {
    return data.che_do === "sso" ? { loai: "chuyen", url: data.url } : { loai: "dang_nhap", veTestbank: data.url };
  }
  return { loai: "loi", status: res.status, message: data.detail ?? `Lỗi ${res.status}`,
           veTestbank: res.headers.get("X-Testbank-Url") };
}

// ── Giáo trình có cấu trúc (mục lục → bài học 4 phần → tiến độ → kiểm tra nhanh) ──
export function getCurriculum(mon = "Toán", khoi = "Lớp 6"): Promise<CurriculumGroup[]> {
  return req(`/curriculum?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
export function getLesson(topicId: number): Promise<Lesson> {
  return req(`/lessons/${topicId}`, { auth: true });
}
export function getProgressMe(mon = "Toán", khoi = "Lớp 6"): Promise<ProgressMe> {
  return req(`/progress/me?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
export function getMyStats(mon = "Toán", khoi = "Lớp 6"): Promise<MyStats> {
  return req(`/me/stats?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
export function setProgress(topicId: number, trangThai: string): Promise<unknown> {
  return req("/progress", { auth: true, body: { topic_id: topicId, trang_thai: trangThai } });
}
export function submitQuiz(topicId: number, answers: number[]): Promise<QuizResult> {
  return req("/quiz/submit", { auth: true, body: { topic_id: topicId, answers } });
}
/** Hỏi trợ lý. `topicId`+`anchor` cho trợ lý đọc ĐÚNG đoạn học sinh đang mở
 *  (xem app/api/tutor.py); thiếu chúng thì chỉ còn SGK như bản cũ.
 *
 *  `phamVi: "ca_cuon"` chuyển sang hỏi xuyên cả cuốn sách của khối đó. Vẫn PHẢI
 *  gửi `topicId`: backend suy môn + khối từ topic để lọc Qdrant và dựng mục lục —
 *  thiếu nó thì rơi về mặc định lớp 6. `anchor` khi đó bị bỏ (không hỏi về đoạn
 *  nào cụ thể), gửi kèm cũng vô hại. */
export function askTutor(
  question: string,
  mon = "Toán",
  opts: { topicId?: number; anchor?: Neo | null; context?: string; phamVi?: PhamVi } = {},
): Promise<TutorAnswer> {
  return req("/tutor/ask", {
    auth: true,
    body: {
      question, mon, topic_id: opts.topicId, anchor: opts.anchor ?? undefined,
      context: opts.context,
      // Không gửi khi là "bai": để backend dùng mặc định, và request của client
      // cũ với client mới ở chế độ thường trông giống nhau -> dễ so khi debug.
      pham_vi: opts.phamVi === "ca_cuon" ? "ca_cuon" : undefined,
    },
  });
}
/** Giới hạn ô nhập (đọc từ server — settings.chat_max_chars override được bằng env).
 *
 *  Cache theo phiên: một bài có thể mở nhiều thẻ trợ lý cùng lúc, mỗi thẻ tự gọi
 *  là N request cho một con số không đổi. Lỗi thì KHÔNG cache để lần sau còn thử
 *  lại (mạng chập một nhịp không nên khoá con số fallback đến hết phiên). */
let _limits: Promise<TutorLimits> | null = null;
export type TutorLimits = { max_chars: number; bao_tri: boolean; bao_tri_nhan: string };
export function getTutorLimits(): Promise<TutorLimits> {
  if (!_limits) {
    _limits = req<TutorLimits>("/tutor/limits", { auth: true })
      .catch((e) => { _limits = null; throw e; });
  }
  return _limits;
}

export { ApiError };

/** Ping thời gian học — gửi "vừa học thêm k giây", KHÔNG gửi tổng. */
export function pingPhien(topicId: number, giay = 30, phan_doc: string[] = []):
  Promise<{ so_giay_phien: number }> {
  return req("/me/phien", { auth: true, body: { topic_id: topicId, giay, phan_doc } });
}
/** §3.5 — trang ôn tập của một mạch / học kỳ. */
export function getOnTap(pham_vi: "mach" | "hoc_ky", gia_tri: string,
                         mon = "Toán", khoi = "Lớp 6"): Promise<OnTap> {
  return req(`/on-tap?pham_vi=${pham_vi}&gia_tri=${encodeURIComponent(gia_tri)}`
    + `&mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}

/** Đề ôn tập (gom từ đề của từng bài, không sinh mới). */
export function getDeOnTap(pham_vi: "mach" | "hoc_ky", gia_tri: string,
                           mon = "Toán", khoi = "Lớp 6"): Promise<DeOnTap> {
  return req(`/on-tap/de?pham_vi=${pham_vi}&gia_tri=${encodeURIComponent(gia_tri)}`
    + `&mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}

export function submitOnTap(pham_vi: string, gia_tri: string, answers: number[],
                            mon = "Toán", khoi = "Lớp 6"): Promise<QuizResult> {
  return req("/on-tap/submit", { method: "POST", auth: true,
    body: { pham_vi, gia_tri, mon, khoi, answers } });
}

export function getThoiGian(ngay = 14): Promise<ThoiGianHoc> {
  return req(`/me/thoi-gian?ngay=${ngay}`, { auth: true });
}
export function getYcd(mon = "Toán", khoi = "Lớp 6"): Promise<{ mach: YcdMach[] }> {
  return req(`/me/ycd?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}

// ── Đề cuối kỳ rút từ DTP Testbank ──
/** Rút đề. `arIds` = chỉ trong các yêu cầu cần đạt này ("bài làm mới" sau khi
 *  nộp). Đề trả về KHÔNG có đáp án — chấm ở server khi nộp. */
export function rutDeCuoiKy(opts: {
  exam?: string; total?: number; arIds?: string[]; subject?: string; grade?: string;
} = {}): Promise<DeCuoiKy> {
  return req("/exam/cuoi-ky/generate", { auth: true, body: {
    subject: opts.subject ?? "TO", grade: opts.grade ?? "06", exam: opts.exam ?? "CK1",
    total: opts.total ?? 12, ar_ids: opts.arIds?.length ? opts.arIds : undefined,
  } });
}
/** "Test thêm" từ khối Đề xuất (US-27): bài mới chỉ gồm câu của các YCCĐ còn yếu. Lỗi kho đề -> 503
 *  với thông điệp tiếng Việt; không tạo bài nào. */
export function testThem(arIds: string[], boQid: string[], exam?: string): Promise<DeCuoiKy> {
  return req("/exam/cuoi-ky/test-them", { auth: true, body: { ar_ids: arIds, bo_qid: boQid, exam } });
}
/** Nộp bài. `traLoi`: qid -> "B" | "A,C" | "Đ,S,Đ,S" | đáp số đã điền. */
export function nopDeCuoiKy(deId: string, traLoi: Record<string, string>): Promise<KetQuaCuoiKy> {
  return req("/exam/cuoi-ky/submit", { auth: true, body: { de_id: deId, tra_loi: traLoi } });
}
/** Lịch sử đề cuối kỳ của chính mình, mới nhất trước, phân trang.
 *  `exam` lọc theo kỳ (CK1/CK2); `con_nua` = còn trang sau. */
export function dsDeCuoiKy(exam?: string, trang: { gioiHan?: number; boQua?: number } = {}):
  Promise<{ de: DeCuoiKyTomTat[]; con_nua: boolean }> {
  const q = new URLSearchParams();
  if (exam) q.set("exam", exam);
  q.set("gioi_han", String(trang.gioiHan ?? 10));
  if (trang.boQua) q.set("bo_qua", String(trang.boQua));
  return req(`/exam/cuoi-ky?${q}`, { auth: true });
}
/** Xoá HẲN một đề (cả lần nộp + chi tiết từng câu). Không khôi phục được. */
export function xoaDeCuoiKy(deId: string): Promise<void> {
  return req(`/exam/cuoi-ky/${encodeURIComponent(deId)}`, { method: "DELETE", auth: true });
}
/** Xoá HẲN mọi đề của mình (chỉ kỳ `exam` nếu có). */
export function xoaHetDeCuoiKy(exam?: string): Promise<{ da_xoa: number }> {
  return req(`/exam/cuoi-ky${exam ? `?exam=${encodeURIComponent(exam)}` : ""}`,
    { method: "DELETE", auth: true });
}
/** Mở lại một đề: chưa nộp thì như lúc rút (không đáp án), đã nộp thì kèm `ket_qua`. */
export function moDeCuoiKy(deId: string): Promise<DeCuoiKy> {
  return req(`/exam/cuoi-ky/${encodeURIComponent(deId)}`, { auth: true });
}

// ── Bài theo mã thầy cô phát trên Testbank (US-29) ──
export function cheDoNhapMa(): Promise<CheDoNhapMa> {
  return req("/exam/ma/cau-hinh", { auth: true });
}
/** Nhập mã: vào thi lần đầu hoặc mở lại đúng bài cũ. 404 mã sai / đã đóng, 422 sai định dạng,
 *  429 nhập sai nhiều lần, 503 Testbank bận — `message` là câu tiếng Việt để hiện thẳng. */
export function vaoMaTestbank(ma: string): Promise<BaiMa> {
  return req("/exam/ma/vao", { auth: true, body: { ma } });
}
export function moBaiMa(deId: string): Promise<BaiMa> {
  return req(`/exam/ma/${encodeURIComponent(deId)}`, { auth: true });
}
export interface TraLoiMot { stt: number; chon: string; seq: number }
/** Lưu dần. `da_nop: true` = bài đã nộp (hết giờ / thầy cô đóng bài) -> `bai` là kết quả. */
export function luuBaiMa(deId: string, cau: TraLoiMot[]):
  Promise<{ da_nop: false; da_luu: number[]; loi: unknown[] } | { da_nop: true; bai: BaiMa }> {
  return req(`/exam/ma/${encodeURIComponent(deId)}/tra-loi`, { method: "PUT", auth: true, body: { cau } });
}
export function nopBaiMa(deId: string, cau: TraLoiMot[]): Promise<BaiMa> {
  return req(`/exam/ma/${encodeURIComponent(deId)}/nop`, { auth: true, body: { cau } });
}

/** Rút một lượt "Luyện thêm từ kho đề" của bài (tối đa 4 câu, không có đáp án). */
export function rutLuyenThem(topicId: number): Promise<DeLuyenThem> {
  return req(`/lessons/${topicId}/luyen-them`, { auth: true, body: {} });
}
/** Nộp lượt luyện thêm. `traLoi`: qid -> "B" | "A,C" | "Đ,S,Đ,S" | đáp số đã điền. */
export function nopLuyenThem(deId: string, traLoi: Record<string, string>): Promise<KetQuaLuyenThem> {
  return req("/lessons/luyen-them/submit", { auth: true, body: { de_id: deId, tra_loi: traLoi } });
}
