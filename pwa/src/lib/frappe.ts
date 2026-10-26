import { apiBase } from "./config";
import { getAccessToken } from "./auth";
import { ApiError } from "./api-error";
import { fetchWithTimeout } from "./fetch";

export { ApiError } from "./api-error";

type FrappeResponse<T> = {
  message?: T;
  exc?: string;
  exc_type?: string;
  _server_messages?: string;
};

async function parseFrappe<T>(res: Response): Promise<T> {
  const data = (await res.json()) as FrappeResponse<T>;
  if (!res.ok) {
    throw new ApiError(data.exc || res.statusText, res.status);
  }
  if (data.exc) {
    throw new ApiError(data.exc, res.status);
  }
  return (data.message ?? data) as T;
}

export async function callMethod<T>(
  method: string,
  args: Record<string, unknown> = {},
  options?: { guest?: boolean; timeoutMs?: number },
): Promise<T> {
  const base = apiBase();
  const url = `${base}/api/method/${method}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (!options?.guest) {
    const token = getAccessToken();
    if (!token) throw new ApiError("Not authenticated");
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetchWithTimeout(
    url,
    {
      method: "POST",
      headers,
      body: JSON.stringify(args),
      credentials: "include",
    },
    options?.timeoutMs,
  );
  return parseFrappe<T>(res);
}

export async function healthCheck(): Promise<{ ok: boolean }> {
  return callMethod("erp_analysis.api.health", {}, { guest: true });
}

export async function fetchClientId(): Promise<string> {
  const base = apiBase();
  const res = await fetchWithTimeout(`${base}/api/method/erp_analysis.config.get_client_id`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = (await res.json()) as { message?: { client_id?: string }; client_id?: string };
  const client_id = data.message?.client_id ?? data.client_id;
  if (!client_id) throw new ApiError("OAuth client_id not configured on server");
  return client_id;
}
