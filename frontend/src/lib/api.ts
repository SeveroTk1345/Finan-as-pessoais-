// Cliente da API. Tudo passa por aqui: mesma origem, cookie de sessão HttpOnly,
// cabeçalho anti-CSRF e chave de idempotência nas operações que criam registros.

export class ApiError extends Error {
  status: number;
  fields: Record<string, string>;
  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

/** Falha de rede: o pedido pode ou não ter chegado ao servidor. */
export class NetworkError extends Error {
  constructor() {
    super("Sem conexão com o servidor. Verifique a internet e tente de novo.");
  }
}

type Listener = (online: boolean) => void;
const listeners = new Set<Listener>();
let lastOnline = true;

export function onServerStatus(fn: Listener): () => void {
  listeners.add(fn);
  fn(lastOnline);
  return () => listeners.delete(fn);
}

function setOnline(value: boolean): void {
  if (value === lastOnline) return;
  lastOnline = value;
  listeners.forEach((fn) => fn(value));
}

let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: () => void): void {
  unauthorizedHandler = fn;
}

const TIMEOUT_MS = 20000;

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "fetch", ...extraHeaders };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    });
  } catch {
    setOnline(false);
    throw new NetworkError();
  } finally {
    clearTimeout(timer);
  }
  setOnline(true);
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const d = (data ?? {}) as { detail?: string; campos?: Record<string, string> };
    if (res.status === 401 && path !== "/auth/entrar") unauthorizedHandler?.();
    throw new ApiError(res.status, d.detail ?? "Algo deu errado. Tente de novo.", d.campos ?? {});
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  /** Alteração simples (sem criar registro financeiro). */
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  /** Define um valor (repetir o pedido dá o mesmo resultado). */
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  /** Criação idempotente: a mesma chave em todas as tentativas da mesma operação. */
  create: <T>(path: string, body: unknown, key: string) =>
    request<T>("POST", path, body, { "Idempotency-Key": key }),
};

/** Chave aleatória de operação (base64url, 24 caracteres). */
export function newOperationKey(): string {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function checkServer(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    const res = await fetch("/api/health", { cache: "no-store", signal: controller.signal });
    clearTimeout(timer);
    setOnline(res.ok);
    return res.ok;
  } catch {
    setOnline(false);
    return false;
  }
}
