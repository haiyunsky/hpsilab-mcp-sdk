import { describe, expect, it } from "vitest";
import { HPSILabClient } from "../src/client";
import { AuthenticationError, ValidationError } from "../src/errors";
import { getRateLimit } from "../src/http";
import { mockResponse, sequenceFetch } from "./testUtils";

function client(fetch: ReturnType<typeof sequenceFetch>["fetch"], apiKey?: string) {
  return new HPSILabClient({ apiKey, fetch, retries: 0 });
}

describe("HPSILabClient — request shape per method", () => {
  it("analyzeStock: GET /api/analyze_stock/{symbol}, refresh as a query param", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { symbol: "NVDA" } })]);
    const c = client(fetch, "hpsi_test");

    await c.analyzeStock("NVDA", { refresh: true });

    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/api/analyze_stock/NVDA");
    expect(url.searchParams.get("refresh")).toBe("true");
    expect(calls[0]?.method).toBe("GET");
  });

  it("getAiPrediction: GET /api/ai_prediction/{symbol}", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: [] })]);
    await client(fetch, "k").getAiPrediction("TSLA");
    expect(new URL(calls[0]!.url).pathname).toBe("/api/ai_prediction/TSLA");
  });

  it("getIvRadar: GET /api/iv_batch?symbols={symbol}", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { status: "success", count: 0, results: [] } })]);
    await client(fetch, "k").getIvRadar("SPY");
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/api/iv_batch");
    expect(url.searchParams.get("symbols")).toBe("SPY");
  });

  it("getOptionPressure: GET /api/option_pressure/{symbol}", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { status: "success", symbol: "SPY" } })]);
    await client(fetch, "k").getOptionPressure("SPY");
    expect(new URL(calls[0]!.url).pathname).toBe("/api/option_pressure/SPY");
  });

  it("getMonteCarlo: GET /api/monte_carlo/{symbol}", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { ticker: "AAPL" } })]);
    await client(fetch, "k").getMonteCarlo("AAPL");
    expect(new URL(calls[0]!.url).pathname).toBe("/api/monte_carlo/AAPL");
  });

  it("getEquityCurves: GET /api/equity_curve/{symbol} (no singular alias shipped)", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { status: "success", ticker: "IONQ" } })]);
    await client(fetch, "k").getEquityCurves("IONQ");
    expect(new URL(calls[0]!.url).pathname).toBe("/api/equity_curve/IONQ");
    expect((client(fetch, "k") as unknown as Record<string, unknown>).getEquityCurve).toBeUndefined();
  });

  it("getPretradeRiskScan: GET /api/pretrade-risk-scan?symbol={symbol}, works anonymously", async () => {
    const { fetch, calls } = sequenceFetch([
      mockResponse({ status: 200, body: { symbol: "NVDA", riskDeltas: [] } }),
    ]);
    // No apiKey — must NOT throw a client-side guard, unlike generateStockResearchReport.
    await client(fetch).getPretradeRiskScan("NVDA");
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/api/pretrade-risk-scan");
    expect(url.searchParams.get("symbol")).toBe("NVDA");
    expect(calls[0]?.headers["x-mcp-anonymous-readonly"]).toBe("1");
  });

  it("generateStockImages: POST /api/stock_report/{symbol}/images with force + types", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { symbol: "NVDA", images: [] } })]);
    await client(fetch, "k").generateStockImages("NVDA", { force: true, types: ["iv_radar", "monte_carlo"] });
    const url = new URL(calls[0]!.url);
    expect(calls[0]?.method).toBe("POST");
    expect(url.pathname).toBe("/api/stock_report/NVDA/images");
    expect(url.searchParams.get("force")).toBe("true");
    expect(url.searchParams.get("types")).toBe("iv_radar,monte_carlo");
  });

  it("generateStockResearchReport: POST .../research_report with refresh + force_images", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { symbol: "NVDA", status: "ok" } })]);
    await client(fetch, "hpsi_test").generateStockResearchReport("NVDA", { refresh: true, forceImages: true });
    const url = new URL(calls[0]!.url);
    expect(url.pathname).toBe("/api/stock_report/NVDA/research_report");
    expect(url.searchParams.get("refresh")).toBe("true");
    expect(url.searchParams.get("force_images")).toBe("true");
  });

  it("does NOT uppercase the symbol client-side — matches the Python SDK's " +
    "_clean_symbol (strip only); every backend route uppercases server-side",
  async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { symbol: "NVDA" } })]);
    await client(fetch, "k").analyzeStock("  nvda  ");
    expect(new URL(calls[0]!.url).pathname).toBe("/api/analyze_stock/nvda");
  });
});

describe("HPSILabClient — input validation", () => {
  it("throws ValidationError for an empty symbol without calling fetch", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: {} })]);
    const c = client(fetch, "k");

    await expect(c.analyzeStock("   ")).rejects.toBeInstanceOf(ValidationError);
    expect(calls).toHaveLength(0);
  });

  it("throws ValidationError for a non-string symbol", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: {} })]);
    const c = client(fetch, "k");

    // @ts-expect-error deliberately passing a non-string to exercise the runtime guard
    await expect(c.getMonteCarlo(123)).rejects.toBeInstanceOf(ValidationError);
    expect(calls).toHaveLength(0);
  });
});

describe("HPSILabClient — generateStockResearchReport auth pre-check", () => {
  it("throws AuthenticationError immediately when no apiKey is configured, without calling fetch", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: {} })]);
    const c = client(fetch); // no apiKey

    const err = await c.generateStockResearchReport("NVDA").catch((e: unknown) => e);

    expect(err).toBeInstanceOf(AuthenticationError);
    expect((err as AuthenticationError).status).toBe(401);
    expect((err as Error).message).toMatch(/requires an API key/i);
    expect(calls).toHaveLength(0);
  });

  it("proceeds to the network when an apiKey is configured", async () => {
    const { fetch, calls } = sequenceFetch([mockResponse({ status: 200, body: { symbol: "NVDA", status: "ok" } })]);
    const c = client(fetch, "hpsi_test");

    await c.generateStockResearchReport("NVDA");

    expect(calls).toHaveLength(1);
  });
});

describe("HPSILabClient — rate limit metadata", () => {
  it("getRateLimit(result) reads the rate-limit data attached to that specific response", async () => {
    const { fetch } = sequenceFetch([
      mockResponse({
        status: 200,
        body: { symbol: "NVDA" },
        headers: {
          "X-RateLimit-Limit": "20000",
          "X-RateLimit-Remaining": "19998",
          "X-RateLimit-Limit-Minute": "200",
          "X-RateLimit-Remaining-Minute": "197",
        },
      }),
    ]);
    const c = client(fetch, "k");

    const result = await c.analyzeStock("NVDA");

    expect(getRateLimit(result)).toEqual({
      limit: 20000,
      remaining: 19998,
      limitPerMinute: 200,
      remainingPerMinute: 197,
    });
    // Hidden property: doesn't pollute the JSON shape callers see.
    expect(Object.keys(result)).toEqual(["symbol"]);
  });

  it("stays correct per-call when one client instance serves concurrent requests " +
    "(the bug the per-response design fixes: a mutable client.lastRateLimit field " +
    "would let one caller's data get overwritten by another's concurrent response)",
  async () => {
    const { fetch } = sequenceFetch([
      mockResponse({ status: 200, body: { symbol: "NVDA" }, headers: { "X-RateLimit-Remaining": "1" } }),
      mockResponse({ status: 200, body: { ticker: "AAPL" }, headers: { "X-RateLimit-Remaining": "9999" } }),
    ]);
    // One shared client instance, as a Node server handling two users concurrently would use it.
    const c = client(fetch, "k");

    const [analyzeResult, monteCarloResult] = await Promise.all([
      c.analyzeStock("NVDA"),
      c.getMonteCarlo("AAPL"),
    ]);

    expect(getRateLimit(analyzeResult)?.remaining).toBe(1);
    expect(getRateLimit(monteCarloResult)?.remaining).toBe(9999);
  });
});
