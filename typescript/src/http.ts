import { ANONYMOUS_READONLY_HEADER, type ResolvedConfig } from "./config";
import {
  APIError,
  AuthenticationError,
  NetworkError,
  PaymentError,
  RateLimitError,
  ResponseError,
  TimeoutError,
} from "./errors";

export interface RateLimitInfo {
  limit?: number;
  remaining?: number;
  limitPerMinute?: number;
  remainingPerMinute?: number;
}

type HttpMethod = "GET" | "POST";

/**
 * Rate-limit data is attached to each response value itself (as a hidden,
 * non-enumerable property), not stored on the client instance. A single
 * mutable field on the client (the earlier design) breaks under singleton
 * reuse: a client instance serving many concurrent requests (e.g. in a
 * Node server handling multiple users) would let one caller's rate-limit
 * reading get overwritten by another caller's concurrent response before
 * the first caller ever reads it. Attaching per-response instead means each
 * awaited result carries its own correct data regardless of what else the
 * client is doing concurrently.
 *
 * Same pattern as Stripe's non-enumerable `lastResponse` on returned
 * resources and OpenAI's `.withResponse()` — the property doesn't show up in
 * `for...in`, `Object.keys()`, `JSON.stringify()`, or object spreads, so the
 * return value still looks and serializes like plain API JSON.
 */
const RATE_LIMIT_KEY = "__rateLimit";

function attachRateLimit<T>(data: T, rateLimit: RateLimitInfo): T {
  if (data !== null && typeof data === "object") {
    Object.defineProperty(data, RATE_LIMIT_KEY, {
      value: rateLimit,
      enumerable: false,
      configurable: true,
    });
  }
  return data;
}

/**
 * Reads the rate-limit metadata (X-RateLimit-* headers) attached to a value
 * previously returned by an HPSILabClient method.
 *
 * ```ts
 * const report = await client.generateStockResearchReport("NVDA");
 * const rl = getRateLimit(report); // { limit, remaining, limitPerMinute, remainingPerMinute } | undefined
 * ```
 *
 * Returns undefined for a value that wasn't returned by this SDK (or that
 * carries no rate-limit data, e.g. a plain object you constructed yourself).
 */
export function getRateLimit(result: unknown): RateLimitInfo | undefined {
  if (result === null || typeof result !== "object") return undefined;
  return (result as { [RATE_LIMIT_KEY]?: RateLimitInfo })[RATE_LIMIT_KEY];
}

function parseIntHeader(headers: Headers, name: string): number | undefined {
  const raw = headers.get(name);
  if (raw === null) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) ? value : undefined;
}

/** Parses X-RateLimit-* headers present on every successful response (see
 * backend/app/middleware/rate_limit.py). Never discarded — attached to each
 * response value and readable via the exported `getRateLimit()` helper. */
function parseRateLimit(headers: Headers): RateLimitInfo {
  return {
    limit: parseIntHeader(headers, "x-ratelimit-limit"),
    remaining: parseIntHeader(headers, "x-ratelimit-remaining"),
    limitPerMinute: parseIntHeader(headers, "x-ratelimit-limit-minute"),
    remainingPerMinute: parseIntHeader(headers, "x-ratelimit-remaining-minute"),
  };
}

function parseRetryAfter(headers: Headers): number | undefined {
  const raw = headers.get("retry-after");
  if (raw === null) return undefined;
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) ? seconds : undefined;
}

function extractMessage(bodyText: string, status: number): string {
  if (bodyText) {
    try {
      const parsed: unknown = JSON.parse(bodyText);
      if (parsed && typeof parsed === "object") {
        const record = parsed as Record<string, unknown>;
        // `message`/`error_message` are the human-readable sentences the
        // backend writes for this failure; `detail` is FastAPI's default key
        // for simple HTTPException bodies (401/403/...); `error` is a
        // last-resort fallback since it's often just a machine code (e.g.
        // "rate_limit_exceeded") rather than something meant for display.
        const detail = record.message ?? record.error_message ?? record.detail ?? record.error;
        if (typeof detail === "string" && detail) return detail;
      }
    } catch {
      // fall through to the generic message below
    }
  }
  return `API request failed with status ${status}.`;
}

/** Passthrough of the response body's `upgrade.{register_url,pricing_url}`
 * (see backend/app/middleware/rate_limit.py), when present. */
function extractUpgrade(bodyText: string): { registerUrl?: string; pricingUrl?: string } {
  if (!bodyText) return {};
  try {
    const parsed: unknown = JSON.parse(bodyText);
    if (parsed && typeof parsed === "object") {
      const upgrade = (parsed as Record<string, unknown>).upgrade;
      if (upgrade && typeof upgrade === "object") {
        const record = upgrade as Record<string, unknown>;
        const registerUrl = typeof record.register_url === "string" ? record.register_url : undefined;
        const pricingUrl = typeof record.pricing_url === "string" ? record.pricing_url : undefined;
        return { registerUrl, pricingUrl };
      }
    }
  } catch {
    // no upgrade info available
  }
  return {};
}

/** Warns once per process when an anonymous caller hits a 429, since a
 * script only checking `error.status` would otherwise never see the
 * register/upgrade nudge buried in the response body. Authenticated callers
 * never see it — they already have an account. */
let warnedAnonRateLimit = false;
function warnAnonRateLimited(registerUrl?: string): void {
  if (warnedAnonRateLimit) return;
  warnedAnonRateLimit = true;
  console.warn(
    `hpsilab: anonymous rate limit hit. Register free for a higher quota: ${registerUrl ?? "https://hpsilab.com/register"}`,
  );
}

function isRetryableStatus(status: number): boolean {
  return status === 429 || status >= 500;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Exponential backoff with jitter; honors Retry-After when the server sends one.
 * No Python SDK equivalent — see README "Beyond the Python SDK". */
function backoffDelayMs(attempt: number, retryAfterSeconds?: number): number {
  if (retryAfterSeconds !== undefined) return retryAfterSeconds * 1000;
  const base = 300 * 2 ** attempt;
  const jitter = Math.random() * 100;
  return base + jitter;
}

function buildUrl(baseUrl: string, path: string, params?: Record<string, string | undefined>): string {
  const url = new URL(path, `${baseUrl}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

function buildHeaders(config: ResolvedConfig): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json", ...config.headers };
  if (config.apiKey) {
    headers.Authorization = `Bearer ${config.apiKey}`;
  } else {
    // No key -> anonymous free-trial tier, same opt-in the Python SDK sends.
    headers[ANONYMOUS_READONLY_HEADER] ??= "1";
  }
  return headers;
}

function toAPIError(
  status: number,
  message: string,
  rawResponse: unknown,
  retryAfter?: number,
  upgrade?: { registerUrl?: string; pricingUrl?: string },
): APIError {
  if (status === 401 || status === 403) return new AuthenticationError(message, status, { rawResponse });
  if (status === 402) return new PaymentError(message, status, { rawResponse });
  if (status === 429) {
    return new RateLimitError(message, status, {
      rawResponse,
      retryAfter,
      registerUrl: upgrade?.registerUrl,
      pricingUrl: upgrade?.pricingUrl,
    });
  }
  return new APIError(message, status, { rawResponse });
}

/**
 * Executes one logical request, retrying retryable failures (429, 5xx, network
 * error, timeout) up to `config.retries` times with exponential backoff.
 * `config.retries === 0` means exactly one attempt — no retry loop runs.
 *
 * Returns the parsed response body directly (matching the Python SDK's
 * "just the JSON" return shape) with rate-limit metadata attached as a
 * hidden property — read it with `getRateLimit(result)`.
 */
export async function request<T>(
  config: ResolvedConfig,
  method: HttpMethod,
  path: string,
  params?: Record<string, string | undefined>,
): Promise<T> {
  const url = buildUrl(config.baseUrl, path, params);
  const headers = buildHeaders(config);
  const maxAttempts = config.retries + 1;

  let lastError: unknown;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const isLastAttempt = attempt === maxAttempts - 1;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), config.timeoutMs);

    let response: Response;
    try {
      response = await config.fetchImpl(url, { method, headers, signal: controller.signal });
    } catch (cause) {
      const timedOut = (cause as { name?: string })?.name === "AbortError";
      lastError = timedOut
        ? new TimeoutError(`Request timed out after ${config.timeoutMs}ms.`, { cause })
        : new NetworkError("Request failed before a response was received.", { cause });
      if (!isLastAttempt) {
        await sleep(backoffDelayMs(attempt));
        continue;
      }
      throw lastError;
    } finally {
      clearTimeout(timer);
    }

    const rateLimit = parseRateLimit(response.headers);

    if (response.status >= 400) {
      const bodyText = await response.text();
      let rawResponse: unknown = bodyText;
      try {
        rawResponse = bodyText ? JSON.parse(bodyText) : undefined;
      } catch {
        // keep rawResponse as the raw text
      }
      const retryAfter = parseRetryAfter(response.headers);
      const upgrade = response.status === 429 ? extractUpgrade(bodyText) : undefined;
      const error = toAPIError(response.status, extractMessage(bodyText, response.status), rawResponse, retryAfter, upgrade);

      if (response.status === 429 && !config.apiKey) {
        warnAnonRateLimited(upgrade?.registerUrl);
      }

      if (!isLastAttempt && isRetryableStatus(response.status)) {
        lastError = error;
        await sleep(backoffDelayMs(attempt, retryAfter));
        continue;
      }
      throw error;
    }

    const bodyText = await response.text();
    try {
      const data = (bodyText ? JSON.parse(bodyText) : undefined) as T;
      return attachRateLimit(data, rateLimit);
    } catch (cause) {
      throw new ResponseError("API response was not valid JSON.", response.status, {
        rawResponse: bodyText,
        cause,
      });
    }
  }

  // Unreachable in practice (the loop always throws or returns), but keeps
  // TypeScript's control-flow analysis happy and fails loudly if it ever is.
  throw lastError instanceof Error ? lastError : new NetworkError("Request failed.");
}
