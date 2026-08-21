import { API_BASE } from "./config";
import type {
  CurriculumGroup,
  Lesson,
  MyStats,
  ProgressMe,
  AuthResult,
  Me,
  Neo,
  QuizResult,
  Role,
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
  role: Role,
): Promise<AuthResult> {
  const res = await post<AuthResult>("/auth/register", { email, password, name, role });
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
 *  (xem app/api/tutor.py); thiếu chúng thì chỉ còn SGK như bản cũ. */
export function askTutor(
  question: string,
  mon = "Toán",
  opts: { topicId?: number; anchor?: Neo | null; context?: string } = {},
): Promise<TutorAnswer> {
  return req("/tutor/ask", {
    auth: true,
    body: { question, mon, topic_id: opts.topicId, anchor: opts.anchor ?? undefined, context: opts.context },
  });
}
/** Giới hạn ô nhập (đọc từ server — settings.chat_max_chars override được bằng env).
 *
 *  Cache theo phiên: một bài có thể mở nhiều thẻ trợ lý cùng lúc, mỗi thẻ tự gọi
 *  là N request cho một con số không đổi. Lỗi thì KHÔNG cache để lần sau còn thử
 *  lại (mạng chập một nhịp không nên khoá con số fallback đến hết phiên). */
let _limits: Promise<{ max_chars: number }> | null = null;
export function getTutorLimits(): Promise<{ max_chars: number }> {
  if (!_limits) {
    _limits = req<{ max_chars: number }>("/tutor/limits", { auth: true })
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
export function getThoiGian(ngay = 14): Promise<ThoiGianHoc> {
  return req(`/me/thoi-gian?ngay=${ngay}`, { auth: true });
}
export function getYcd(mon = "Toán", khoi = "Lớp 6"): Promise<{ mach: YcdMach[] }> {
  return req(`/me/ycd?mon=${encodeURIComponent(mon)}&khoi=${encodeURIComponent(khoi)}`, { auth: true });
}
