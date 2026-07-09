import { API_BASE } from "./config";
import type { ChatResponse, Role } from "./types";

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

async function post<T>(path: string, body: unknown, auth = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const t = tokenStore.get();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Lỗi ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      /* giữ detail mặc định */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
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

export function sendChat(message: string, sessionId: string): Promise<ChatResponse> {
  return post<ChatResponse>("/chat", { message, session_id: sessionId }, true);
}

export { ApiError };
