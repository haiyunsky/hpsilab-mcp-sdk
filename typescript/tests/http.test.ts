import { describe, expect, it, vi } from "vitest";
import { resolveConfig } from "../src/config";
import { getRateLimit, request } from "../src/http";
import {
  AuthenticationError,
  NetworkError,
  PaymentError,
  RateLimitError,
  ResponseError,
  TimeoutError,
} from "../src/errors";
import { hangingFetch, mockResponse, networkErrorFetch, sequenceFetch } from "./testUtils";

describe("http.request", () => {
  it("returns parsed JSON and rate-limit headers on success", async () => {
    const { fetch, calls } = sequenceFetch([
      mockResponse({
        status: 200,
        body: { ok: true },
        headers: {
          "X-RateLimit-Limit": "20000",
          "X-RateLimit-Remaining": "19999",
          "X-RateLimit-Limit-Minute": "200",
          "X-RateLimit-Remaining-Minute": "199",
        },
      }),
    ]);
    const config = resolveConfig({ apiKey: "hpsi_test", fetch });

    const data = await request<{ ok: boolean }>(config, "GET", "/api/analyze_stock/NVDA");

    expect(data).toEqual({ ok: true });
    expect(getRateLimit(data)).toEqual({
      limit: 20000,
      remaining: 19999,
      limitPerMinute: 200,
      remainingPerMinute: 199,
    });
    // The hidden property must not leak into normal serialization/enumeration.
    expect(JSON.stringify(data)).toBe('{"ok":true}');
    expect(Object.keys(data)).toEqual(["ok"]);
    expect(calls[0]?.headers.authorization).toBe("Bearer hpsi_test");
  });

  it("getRateLimit() returns undefined for a value with no attached data", () => {
    expect(getRateLimit({ ok: true })).toBeUndefined();
    expect(getRateLimit(null)).toBeUndefined();
    expect(getRateLimit("just a string")).toBeUndefined();
    expect(getRateLimit(42)).toBeUndefined();
  });

  it("attaches rate-limit data to array response bodies too (e.g. getAiPrediction)", async () => {
    const { fetch } = sequenceFetch([
      mockResponse({ status: 200, body: [{ last_close: 1 }], headers: { "X-RateLimit-Remaining": "5" } }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch });

    const data = await request<unknown[]>(config, "GET", "/api/ai_prediction/NVDA");

    expect(Array.isArray(data)).toBe(true);
    expect(getRateLimit(data)?.remaining).toBe(5);
  });

  it("does not mix up rate-limit data between two concurrent requests with different headers", async () => {
    const { fetch } = sequenceFetch([
      mockResponse({ status: 200, body: { who: "A" }, headers: { "X-RateLimit-Remaining": "1" } }),
      mockResponse({ status: 200, body: { who: "B" }, headers: { "X-RateLimit-Remaining": "999" } }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch });

    const [a, b] = await Promise.all([
      request<{ who: string }>(config, "GET", "/x"),
      request<{ who: string }>(config, "GET", "/y"),
    ]);

    expect(getRateLimit(a)?.remaining).toBe(1);
    expect(getRateLimit(b)?.remaining).toBe(999);
  });

  it("sends the anonymous read-only header when no apiKey is set", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: {} })]);
    const config = resolveConfig({ fetch });

    await request(config, "GET", "/api/analyze_stock/NVDA");

    expect(calls[0]?.headers.authorization).toBeUndefined();
    expect(calls[0]?.headers["x-mcp-anonymous-readonly"]).toBe("1");
  });

  it.each([
    [401, AuthenticationError],
    [403, AuthenticationError],
    [402, PaymentError],
    [429, RateLimitError],
  ] as const)("maps HTTP %s to %s", async (status, ErrorClass) => {
    const { fetch } = sequenceFetch([
      mockResponse({ status, body: { detail: "nope" }, headers: status === 429 ? { "Retry-After": "5" } : {} }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    await expect(request(config, "GET", "/api/whatever")).rejects.toBeInstanceOf(ErrorClass);
  });

  it("surfaces the Retry-After seconds on RateLimitError", async () => {
    const { fetch } = sequenceFetch([mockResponse({ status: 429, headers: { "Retry-After": "12" }, body: {} })]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    const err = await request(config, "GET", "/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(RateLimitError);
    expect((err as RateLimitError).retryAfter).toBe(12);
  });

  it("retries a 429 and succeeds on the next attempt", async () => {
    const { fetch, calls } = sequenceFetch([
      mockResponse({ status: 429, headers: { "Retry-After": "0" }, body: { detail: "slow down" } }),
      mockResponse({ status: 200, body: { ok: true } }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 1 });

    const data = await request<{ ok: boolean }>(config, "GET", "/x");

    expect(data).toEqual({ ok: true });
    expect(calls).toHaveLength(2);
  });

  it("does not retry when retries: 0 — exactly one attempt is made", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 429, body: {} })]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    await expect(request(config, "GET", "/x")).rejects.toBeInstanceOf(RateLimitError);
    expect(calls).toHaveLength(1);
  });

  it("does not retry when retry: false — exactly one attempt is made", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 500, body: {} })]);
    const config = resolveConfig({ apiKey: "k", fetch, retry: false });

    await expect(request(config, "GET", "/x")).rejects.toBeInstanceOf(Error);
    expect(calls).toHaveLength(1);
  });

  it("does not retry a non-retryable 4xx like 404", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 404, body: { detail: "not found" } })]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 2 });

    await expect(request(config, "GET", "/x")).rejects.toMatchObject({ status: 404 });
    expect(calls).toHaveLength(1);
  });

  it("throws ResponseError when the body is not valid JSON", async () => {
    const { fetch } = sequenceFetch([mockResponse({ status: 200, bodyText: "<html>not json</html>" })]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    await expect(request(config, "GET", "/x")).rejects.toBeInstanceOf(ResponseError);
  });

  it("throws NetworkError when fetch rejects before any response", async () => {
    const { fetch } = networkErrorFetch();
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    await expect(request(config, "GET", "/x")).rejects.toBeInstanceOf(NetworkError);
  });

  it("throws TimeoutError when the request exceeds timeoutMs", async () => {
    const { fetch } = hangingFetch();
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0, timeoutMs: 20 });

    await expect(request(config, "GET", "/x")).rejects.toBeInstanceOf(TimeoutError);
  });

  it("omits undefined query params instead of sending them as literal 'undefined'", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: {} })]);
    const config = resolveConfig({ apiKey: "k", fetch });

    await request(config, "GET", "/api/analyze_stock/NVDA", { refresh: undefined });

    expect(calls[0]?.url).not.toContain("refresh");
  });

  it("prefers `message` over the machine-readable `error` code", async () => {
    // Backend 429 bodies put a machine-readable code in `error` ahead of the
    // human-readable `message` — the SDK must not surface the code.
    const { fetch } = sequenceFetch([
      mockResponse({
        status: 429,
        body: { error: "rate_limit_exceeded", message: "Daily limit reached. Register free." },
      }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    const err = await request(config, "GET", "/x").catch((e: unknown) => e);
    expect((err as Error).message).toBe("Daily limit reached. Register free.");
  });

  it("attaches registerUrl/pricingUrl from the response body's `upgrade` object", async () => {
    const { fetch } = sequenceFetch([
      mockResponse({
        status: 429,
        body: {
          message: "Daily limit reached.",
          upgrade: { register_url: "https://hpsilab.com/register", pricing_url: "https://hpsilab.com/pricing" },
        },
      }),
    ]);
    const config = resolveConfig({ apiKey: "k", fetch, retries: 0 });

    const err = await request(config, "GET", "/x").catch((e: unknown) => e);
    expect((err as RateLimitError).registerUrl).toBe("https://hpsilab.com/register");
    expect((err as RateLimitError).pricingUrl).toBe("https://hpsilab.com/pricing");
  });

  it("warns once for an anonymous caller on 429, and not for an authenticated one", async () => {
    vi.resetModules();
    const { request: freshRequest } = await import("../src/http");
    const { resolveConfig: freshResolveConfig } = await import("../src/config");
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    try {
      const anon = sequenceFetch([
        mockResponse({ status: 429, body: { message: "Daily limit reached.", upgrade: { register_url: "https://hpsilab.com/register" } } }),
        mockResponse({ status: 429, body: { message: "Daily limit reached." } }),
      ]);
      const anonConfig = freshResolveConfig({ fetch: anon.fetch, retries: 0 });

      await freshRequest(anonConfig, "GET", "/x").catch(() => {});
      expect(warnSpy).toHaveBeenCalledTimes(1);
      expect(warnSpy.mock.calls[0]?.[0]).toContain("https://hpsilab.com/register");

      // Second anon 429 in the same process must not warn again.
      await freshRequest(anonConfig, "GET", "/x").catch(() => {});
      expect(warnSpy).toHaveBeenCalledTimes(1);

      // An authenticated caller never triggers the warning at all.
      const authed = sequenceFetch([mockResponse({ status: 429, body: { message: "Monthly quota exceeded." } })]);
      const authedConfig = freshResolveConfig({ apiKey: "k", fetch: authed.fetch, retries: 0 });
      await freshRequest(authedConfig, "GET", "/x").catch(() => {});
      expect(warnSpy).toHaveBeenCalledTimes(1);
    } finally {
      warnSpy.mockRestore();
    }
  });
});
