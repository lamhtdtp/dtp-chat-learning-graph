import { API_BASE } from "./config";
import type { ChatResponse, MessageRow, Role, SessionRow } from "./types";

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
): Promise<string> {
  const { token } = await post<{ token: string }>("/auth/register", {
    email,
    password,
    name,
    role,
  });
  tokenStore.set(token);
  return token;
}

export async function login(email: string, password: string): Promise<string> {
  const { token } = await post<{ token: string }>("/auth/login", { email, password });
  tokenStore.set(token);
  return token;
}

export function sendChat(message: string, sessionId: number | null): Promise<ChatResponse> {
  return post<ChatResponse>("/chat", { message, session_id: sessionId }, true);
}

export function getSessions(): Promise<SessionRow[]> {
  return req<SessionRow[]>("/sessions", { auth: true });
}

export function getSessionMessages(id: number): Promise<MessageRow[]> {
  return req<MessageRow[]>(`/sessions/${id}`, { auth: true });
}

export function deleteSession(id: number): Promise<void> {
  return req<void>(`/sessions/${id}`, { method: "DELETE", auth: true });
}

export { ApiError };
