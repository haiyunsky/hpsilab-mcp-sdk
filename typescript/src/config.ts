/**
 * Client configuration. No Python SDK equivalent for `retries`/`retry` — the
 * Python client (httpx.Client, no retry loop) fails on the first error. Retry
 * with exponential backoff is a TS-SDK-only addition; see README
 * "Beyond the Python SDK".
 */

export type FetchLike = typeof fetch;

export interface HPSILabClientConfig {
  /** Bearer token (`hpsi_...`). Omit for the anonymous read-only path, same as
   * the Python SDK's `api_key=None` behavior. */
  apiKey?: string;
  /** Defaults to https://hpsilab.com. */
  baseUrl?: string;
  /** Per-request timeout in milliseconds. Defaults to 30_000. */
  timeoutMs?: number;
  /** Max retry attempts for retryable failures (429, 5xx, network/timeout).
   * Defaults to 2. Set to 0 to disable retries entirely — no retry loop runs. */
  retries?: number;
  /** Set to `false` to fully disable retries regardless of `retries`. Shorthand
   * for `{ retries: 0 }`. */
  retry?: boolean;
  /** Extra headers merged into every request. */
  headers?: Record<string, string>;
  /** Override the fetch implementation (tests, non-standard runtimes). Defaults
   * to the global `fetch`. */
  fetch?: FetchLike;
}

/** `HPSILabClientConfig` with every field resolved to a concrete value. */
export interface ResolvedConfig {
  apiKey?: string;
  baseUrl: string;
  timeoutMs: number;
  /** 0 means "retries disabled" — exactly one attempt is made. */
  retries: number;
  headers: Record<string, string>;
  fetchImpl: FetchLike;
}

export const DEFAULT_BASE_URL = "https://hpsilab.com";
export const DEFAULT_TIMEOUT_MS = 30_000;
export const DEFAULT_RETRIES = 2;

/** Header that opts an unauthenticated caller into the backend's anonymous
 * read-only path. Must match the Python SDK's ANONYMOUS_READONLY_HEADER and
 * the backend's MCP_ANONYMOUS_READONLY_HEADER. */
export const ANONYMOUS_READONLY_HEADER = "x-mcp-anonymous-readonly";

export function resolveConfig(options: HPSILabClientConfig): ResolvedConfig {
  const retries = options.retry === false ? 0 : options.retries ?? DEFAULT_RETRIES;
  if (!Number.isInteger(retries) || retries < 0) {
    throw new RangeError("config.retries must be a non-negative integer.");
  }

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new RangeError("config.timeoutMs must be a positive number.");
  }

  const fetchImpl = options.fetch ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error(
      "No fetch implementation available on this runtime. Pass { fetch } explicitly (e.g. from undici or node-fetch).",
    );
  }

  return {
    apiKey: options.apiKey,
    baseUrl: (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, ""),
    timeoutMs,
    retries,
    headers: { ...options.headers },
    fetchImpl,
  };
}
