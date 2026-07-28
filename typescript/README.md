# @hpsilab/sdk

Official TypeScript SDK for the [HPSILab](https://hpsilab.com) quantitative finance
REST API — stock analysis, implied-volatility structure, options positioning,
Monte Carlo simulation, strategy equity curves, next-day AI predictions, and
pre-trade risk scans.

This SDK wraps the same 9 tools as the official
[Python SDK](https://github.com/haiyunsky/hpsilab-mcp-sdk) (`hpsilab-mcp` on
PyPI, client class `HpsiMcpClient`) and the [hpsilab.com MCP server](https://hpsilab.com/mcp),
with method names mirrored 1:1 (camelCased) wherever a Python method exists.
It talks to the REST API directly over `fetch` — it does not implement MCP
transport, tool discovery, or x402 payments. See
["Relationship to MCP and x402"](#relationship-to-mcp-and-x402) below.

## Install

```bash
pnpm add @hpsilab/sdk
# or: npm install @hpsilab/sdk / yarn add @hpsilab/sdk
```

Requires Node 22+ (uses the global `fetch`/`Headers`/`AbortController`, no
polyfills bundled). Ships dual ESM + CJS builds with bundled `.d.ts` types.

## Quick start

```ts
import { HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const result = await client.analyzeStock("NVDA");
console.log(result.signal, result.confidence_score);
```

Get an API key (`hpsi_...` prefix) at **hpsilab.com → Settings → MCP API Keys**.
Free tools work with no key at all — see [Authentication](#authentication).

## Authentication

```ts
// Signed-in
const client = new HPSILabClient({ apiKey: "hpsi_..." });

// Anonymous / free-trial — omit apiKey. The SDK sends the same
// `x-mcp-anonymous-readonly: 1` header the Python SDK sends by default.
const anon = new HPSILabClient();
```

**Not every method behaves the same way anonymously.** The 7 Free tools
(`analyzeStock`, `getAiPrediction`, `getIvRadar`, `getOptionPressure`,
`getMonteCarlo`, `getEquityCurves`, `generateStockImages`) and
`getPretradeRiskScan` accept the anonymous-readonly header and work without a
key. `generateStockResearchReport` does not — its REST route requires a real
token unconditionally, so this SDK throws `AuthenticationError` immediately
(without making a network call) when `apiKey` is missing, rather than letting
a confusing generic 401 come back from the network:

```ts
const anon = new HPSILabClient();
await anon.generateStockResearchReport("NVDA");
// throws AuthenticationError: "generateStockResearchReport requires an API
// key — anonymous access is not available for this endpoint via REST.
// (analyzeStock supports anonymous access via x402 payment at the MCP layer,
// but this REST SDK does not implement x402.)"
```

`getPretradeRiskScan`'s anonymous access is real today but is **not a stable
guarantee** — the backend flag it depends on
(`MCP_ALLOW_ANONYMOUS_READONLY`) is documented server-side as temporary,
"set to false once OAuth is in place." If that happens, anonymous calls to
`getPretradeRiskScan` will start throwing `AuthenticationError` the same way
`generateStockResearchReport` does today. Don't build production logic on
`getPretradeRiskScan` staying anonymous-callable.

## The 9 tools

| Method | Endpoint | Tier |
| --- | --- | --- |
| `analyzeStock(symbol, { refresh? })` | `GET /api/analyze_stock/{symbol}` | Free |
| `getAiPrediction(symbol)` | `GET /api/ai_prediction/{symbol}` | Free |
| `getIvRadar(symbol)` | `GET /api/iv_batch?symbols={symbol}` | Free |
| `getOptionPressure(symbol)` | `GET /api/option_pressure/{symbol}` | Free |
| `getMonteCarlo(symbol)` | `GET /api/monte_carlo/{symbol}` | Free |
| `getEquityCurves(symbol)` | `GET /api/equity_curve/{symbol}` | Free |
| `getPretradeRiskScan(symbol)` | `GET /api/pretrade-risk-scan?symbol={symbol}` | Pro¹ |
| `generateStockImages(symbol, { force?, types? })` | `POST /api/stock_report/{symbol}/images` | Free |
| `generateStockResearchReport(symbol, { refresh?, forceImages? })` | `POST /api/stock_report/{symbol}/research_report` | Pro¹ |

¹ "Pro" is documentation-only in the REST contract — there is no `tier` field
or `x-tier` header on any response. A 403 response means "this tool isn't in
your plan"; a 429 means your daily/per-minute/monthly quota is used up. See
[Error handling](#error-handling).

The Python SDK also exposes a `get_equity_curve` (singular) alias for the
same endpoint as `getEquityCurves`. This SDK ships only `getEquityCurves`,
matching the 9 real tools — the singular alias is legacy and out of scope for
v1.

Runnable examples for all 9 tools, plus retry/error-handling config, are in
[`examples/`](./examples).

## Error handling

Every failure is a typed subclass of `HPSILabError`:

| Class | When | Extends |
| --- | --- | --- |
| `ValidationError` | Bad client-side input (e.g. empty symbol). No network call made. | `HPSILabError` |
| `AuthenticationError` | HTTP 401 (missing/invalid token) or 403 (valid token, tool not in your plan) | `APIError` |
| `PaymentError` | HTTP 402. Reserved for a possible future x402-over-REST flow — **the live backend never returns 402 today** (confirmed against every REST router; 403/429 cover all current gating). | `APIError` |
| `RateLimitError` | HTTP 429. Carries `retryAfter` (seconds) from the `Retry-After` header when present. | `APIError` |
| `ResponseError` | The response body wasn't valid JSON. | `APIError` |
| `NetworkError` | The request failed before any response was received (DNS/TCP/TLS/abort). | `HPSILabError` |
| `TimeoutError` | The request exceeded `timeoutMs`. | `NetworkError` |
| `APIError` | Any other HTTP error status. | `HPSILabError` |

```ts
import { AuthenticationError, RateLimitError, ValidationError } from "@hpsilab/sdk";

try {
  await client.analyzeStock(symbol);
} catch (err) {
  if (err instanceof ValidationError) { /* fix your input */ }
  else if (err instanceof AuthenticationError) { /* bad/missing key, or not in your plan */ }
  else if (err instanceof RateLimitError) { /* back off err.retryAfter seconds */ }
  else throw err;
}
```

Every `APIError` (and subclass) carries `status`, `rawResponse` (the parsed
JSON body or raw text), and `requestId?: string | undefined`. `requestId` is
always `undefined` today — the backend does not send a request-id response
header (confirmed against `app/middleware/request_log.py`). It's typed for
forward compatibility only; this SDK never fabricates a value for it.

## Rate limiting

Every successful response carries `X-RateLimit-Limit`,
`X-RateLimit-Remaining`, `X-RateLimit-Limit-Minute`, and
`X-RateLimit-Remaining-Minute` headers. The SDK parses these and attaches them
to the returned value itself — read them with the exported `getRateLimit()`
helper:

```ts
import { getRateLimit, HPSILabClient } from "@hpsilab/sdk";

const client = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

const result = await client.analyzeStock("NVDA");
console.log(getRateLimit(result));
// { limit: 20000, remaining: 19999, limitPerMinute: 200, remainingPerMinute: 199 }
```

Rate-limit data is attached per-response as a hidden, non-enumerable
property (same pattern as Stripe's `lastResponse` on returned resources, or
OpenAI's `.withResponse()`) — it never shows up in `JSON.stringify(result)`,
`Object.keys(result)`, `for...in`, or object spreads, so `result` still looks
and serializes exactly like the plain API JSON body.

This is deliberately **not** a mutable field on the client instance. A single
`client.lastRateLimit`-style field breaks under the common pattern of one
`HPSILabClient` instance serving concurrent requests (e.g. a Node server
handling multiple users on a shared client) — a fast response for User B
could overwrite the field before User A ever reads their own result. Because
the data now travels on the response value itself, each awaited call gets
its own correct reading regardless of what else the client is doing
concurrently:

```ts
const [a, b] = await Promise.all([
  client.getAiPrediction("A"),
  client.getIvRadar("B"),
]);
getRateLimit(a); // A's own rate-limit headers, unaffected by B's response
getRateLimit(b); // B's own rate-limit headers, unaffected by A's response
```

`getRateLimit()` returns `undefined` for any value it didn't attach data to
(a plain object you constructed yourself, `null`, a primitive, etc.).

## Pagination

None of the 9 endpoints paginate — there's nothing to page through (single-
symbol lookups and aggregate reports). No pagination helpers are implemented
in v1. If a future endpoint adds real `page`/`cursor`/`limit` params, this
section will be updated accordingly.

## Configuration

```ts
new HPSILabClient({
  apiKey: "hpsi_...",       // omit for anonymous read-only access
  baseUrl: "https://hpsilab.com", // default
  timeoutMs: 30_000,        // default; per-request timeout
  retries: 2,               // default; 0 disables retries entirely
  retry: false,              // shorthand for { retries: 0 }
  headers: { "X-My-Header": "value" }, // merged into every request
  fetch: myCustomFetch,     // override the fetch implementation
});
```

## Beyond the Python SDK

Two things in this SDK have **no equivalent** in the Python SDK or the REST
API contract itself — don't mistake them for guaranteed server-side behavior:

- **`ValidationError`.** The Python SDK raises a bare `ValueError`/`TypeError`
  for an empty/invalid symbol, not a typed SDK exception. This SDK adds a
  proper `ValidationError` class for the same client-side check (empty or
  non-string symbol) — it never reaches the network.
- **Retry with exponential backoff.** The Python SDK (`httpx.Client`, no
  retry loop) fails on the first error, full stop. This SDK retries
  retryable failures (429, 5xx, network error, timeout) up to `retries`
  times (default 2) with exponential backoff + jitter, honoring `Retry-After`
  when the server sends one. Set `retries: 0` or `retry: false` to match the
  Python SDK's fail-fast behavior exactly — no retry loop runs in that case.

Everything else (method names, parameters, endpoint mapping, error status
code -> class mapping) mirrors the Python SDK / REST API as closely as a TS
SDK reasonably can.

## Relationship to MCP and x402

`hpsilab.com` exposes the same 9 tools three ways: this REST SDK, the
[Python REST SDK](https://github.com/haiyunsky/hpsilab-mcp-sdk), and a
[remote MCP server](https://hpsilab.com/mcp) (Streamable HTTP,
`Authorization: Bearer <token>`). This package implements **REST + API key
only**. It does not implement:

- MCP transport, tool discovery, or the MCP protocol in any form
- [x402](https://x402.org) pay-per-call (anonymous USDC micropayments on
  Base) — x402 exists only at the MCP layer (`get_pretrade_risk_scan` $0.15,
  `generate_stock_research_report` $0.35). An anonymous MCP agent can pay per
  call there; an anonymous REST caller using this SDK cannot — see
  [Authentication](#authentication) above for exactly which methods that
  affects.

If you need MCP transport or x402, connect an MCP client directly to
`https://hpsilab.com/mcp` instead of using this SDK.

## Known limitations

- **`getPretradeRiskScan`'s anonymous access is not a stable guarantee.** See
  [Authentication](#authentication).
- **`requestId` is always `undefined`.** The backend sends no request-id
  header today. See [Error handling](#error-handling).
- **Types are hand-derived, not spec-generated.** There is no OpenAPI spec —
  `https://hpsilab.com/api/openapi.json` 404s, and the only written reference
  is a hand-maintained markdown file in the Python SDK repo. `src/types.ts`
  was built by reading the actual FastAPI route handlers (see the file header
  for exact source paths per type). If the backend response shape changes,
  these types can silently drift — there's no build-time check against the
  live API. Re-sync by hand if you notice a mismatch.

## Development

```bash
pnpm install
pnpm build       # tsup -> dist/ (ESM + CJS + .d.ts)
pnpm typecheck   # tsc --noEmit
pnpm test        # vitest
pnpm lint        # eslint
```

CI (`.github/workflows/ci.yml`) runs lint, typecheck, test, and build in that
order on every PR and on push to `master` — a failure at any step stops the
rest.

## Releasing

Versioning and publishing are automated with
[Changesets](https://github.com/changesets/changesets). As a contributor, you
never bump `package.json`'s version or write `CHANGELOG.md` by hand:

1. Make your change.
2. Run `pnpm changeset` and describe it (patch/minor/major + a one-line
   summary). This writes a small markdown file under `.changeset/` — commit
   it alongside your change.
3. Open a PR as usual.
4. Once merged to `master`, the release workflow
   (`.github/workflows/release.yml`) notices the pending changeset and
   opens (or updates) a **"Version Packages"** PR that bumps the version and
   updates `CHANGELOG.md` for you — you don't write either by hand.
5. Merging *that* PR triggers the same workflow again; this time it builds,
   publishes `@hpsilab/sdk` to npm with
   [provenance](https://docs.npmjs.com/generating-provenance-statements), and
   pushes the version-bump commit plus a git tag.

Publishing requires a repo secret `NPM_TOKEN` (an npm automation token with
publish rights on the `@hpsilab` scope) — see the comment at the top of
`release.yml` for where to set it. No `NPM_TOKEN` means the version PR still
gets created/updated fine; only the final publish step fails once merged.

## License

MIT
