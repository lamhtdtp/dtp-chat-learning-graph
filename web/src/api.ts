import { API_BASE } from "./config";
import type {
  AuthResult,
  ChatResponse,
  ExamResult,
  MessageRow,
  QuizData,
  Role,
  SessionRow,
  VideoInfo,
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

export function getMe(): Promise<{ id: number; email: string; name: string; role: Role }> {
  return req("/auth/me", { auth: true });
}

export function generateExam(hoc_ky: string, tong_so_cau: number, mon = "Toán"): Promise<ExamResult> {
  return post<ExamResult>("/exam/generate", { hoc_ky, tong_so_cau, mon }, true);
}

// Học sinh: đề NGẮN bám ma trận (như giáo viên), không cần quyền giáo viên.
export function generatePracticeExam(hoc_ky = "hk1", tong_so_cau = 5): Promise<ExamResult> {
  return post<ExamResult>("/exam/practice", { hoc_ky, tong_so_cau }, true);
}

export function sendChat(message: string, sessionId: number | null, subject = "toan"): Promise<ChatResponse> {
  return post<ChatResponse>("/chat", { message, session_id: sessionId, subject }, true);
}

export function getSessions(subject?: string): Promise<SessionRow[]> {
  const q = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return req<SessionRow[]>(`/sessions${q}`, { auth: true });
}

export function getSessionMessages(id: number): Promise<MessageRow[]> {
  return req<MessageRow[]>(`/sessions/${id}`, { auth: true });
}

export function deleteSession(id: number): Promise<void> {
  return req<void>(`/sessions/${id}`, { method: "DELETE", auth: true });
}

export function getVideoStatus(jobId: number): Promise<VideoInfo> {
  return req<VideoInfo>(`/video/jobs/${jobId}`);
}

export function generateVideo(conceptKey: string): Promise<VideoInfo> {
  return post<VideoInfo>("/video/generate", { concept_key: conceptKey }, true);
}

export function getItestQuiz(topic: string): Promise<QuizData> {
  return req<QuizData>(`/itest/quiz?topic=${encodeURIComponent(topic)}`, { auth: true });
}

// Lấy URL ẢNH TRANG SGK đã KÝ (có hạn) — thẻ <img> không gửi được Bearer nên
// phải xin link ký qua endpoint auth này rồi mới gán vào src.
export function getBookPageUrl(tap: number, page: number, mon = "toan"): Promise<{ url: string }> {
  return req<{ url: string }>(`/books/pages-url/${encodeURIComponent(mon)}/${tap}/${page}`, { auth: true });
}

export function getBookPageSummary(tap: number, page: number, mon = "toan"): Promise<{ summary: string | null }> {
  return req<{ summary: string | null }>(`/books/summary/${encodeURIComponent(mon)}/${tap}/${page}`, { auth: true });
}

// Danh mục chương trình (panel chủ đề trong chat) — lấy từ taxonomy backend.
export interface TopicItem { ten: string; co_video: boolean }
export interface TopicGroupRow { mach_noi_dung: string; items: TopicItem[]; co_video: boolean }

export function getTopics(mon = "Toán"): Promise<TopicGroupRow[]> {
  return req(`/books/topics?mon=${encodeURIComponent(mon)}`, { auth: true });
}

export { ApiError };
