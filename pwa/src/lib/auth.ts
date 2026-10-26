import { apiBase } from "./config";
import { fetchWithTimeout } from "./fetch";
import { ApiError } from "./frappe";
import { clearUserCache } from "./localCache";

const TOKEN_KEY = "printechs_pwa_token";
const USER_KEY = "printechs_pwa_user";

export type TokenResponse = {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
  user?: string;
  full_name?: string;
};

export type StoredSession = {
  access_token: string;
  email: string;
  full_name?: string;
};

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getSessionUser(): StoredSession | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredSession;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  const user = getSessionUser();
  if (user?.email) clearUserCache(user.email);
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function saveSession(token: string, email: string, full_name?: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({ access_token: token, email, full_name }),
  );
}

function parseLoginPayload(data: Record<string, unknown>): TokenResponse {
  if (data.exc || data.exc_type === "AuthenticationError") {
    throw new ApiError("Invalid email or password");
  }
  const msg = data.message;
  const payload = (
    typeof msg === "object" && msg !== null ? msg : data
  ) as TokenResponse & { error?: string };
  if (payload.error || data.error) {
    throw new ApiError(String(payload.error || data.error || "Login failed"));
  }
  return payload;
}

/** Same outcome as mobile OAuth password grant, via a single ERP Analysis endpoint. */
export async function loginWithPassword(
  username: string,
  password: string,
): Promise<StoredSession> {
  const base = apiBase();
  const res = await fetchWithTimeout(`${base}/api/method/erp_analysis.api.pwa_password_login`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ usr: username.trim(), pwd: password }),
  });
  let data: Record<string, unknown>;
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    throw new ApiError("Unexpected response from server", res.status);
  }
  if (!res.ok && !data.exc) {
    throw new ApiError("Login failed", res.status);
  }
  const payload = parseLoginPayload(data);
  const access_token = payload.access_token;
  if (!access_token) throw new ApiError("No access_token in response");
  const email = (payload.user || username).trim();
  saveSession(access_token, email, payload.full_name);
  return { access_token, email, full_name: payload.full_name };
}
