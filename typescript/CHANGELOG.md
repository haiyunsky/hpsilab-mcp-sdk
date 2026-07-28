# @hpsilab/sdk

## 0.2.0

### Minor Changes

- 2cc8509: Fixed `RateLimitError` (and every other API error) surfacing the backend's machine-readable `error` code (e.g. `"rate_limit_exceeded"`) instead of its human-readable `message`/`error_message` — the friendly sentence now wins.

  Added: anonymous (no `apiKey`) callers now get a one-time `console.warn()` when they hit a 429, pointing at `hpsilab.com/register` (or the backend's own `upgrade.register_url` when present) — visible even to scripts that only check `error.status`. Authenticated callers never see it. `RateLimitError` also gains optional `registerUrl`/`pricingUrl` fields passthrough from the response body's `upgrade` object.

## 0.1.0

### Minor Changes

- 4e633a4: Initial release of the official TypeScript SDK for the HPSILab quantitative finance REST API.

  - **Flat 9-method client** (`HPSILabClient`), mirroring the Python SDK's `HpsiMcpClient` 1:1 by tool name, camelCased — no submodules: `analyzeStock`, `getAiPrediction`, `getIvRadar`, `getOptionPressure`, `getMonteCarlo`, `getEquityCurves`, `getPretradeRiskScan`, `generateStockImages`, `generateStockResearchReport`.
  - **Typed error hierarchy** (`HPSILabError` -> `APIError` -> `AuthenticationError` / `PaymentError` / `RateLimitError` / `ResponseError`, plus `NetworkError` -> `TimeoutError`, and a client-side-only `ValidationError`) mapping every REST failure mode to a specific, catchable class instead of opaque HTTP errors.
  - **Configurable retry with exponential backoff** on 429/5xx/timeout/network failures, honoring `Retry-After` when the server sends one — fully disable-able via `{ retries: 0 }` or `{ retry: false }` for exact-once request semantics.
  - **Per-response rate-limit tracking** via the exported `getRateLimit(result)` helper: `X-RateLimit-*` headers are attached to each response value as a non-enumerable property (not a mutable client field), so a single client instance stays correct under concurrent calls instead of one caller's data getting overwritten by another's.
  - **Hand-derived response types** for all 9 tools, built directly from the backend's FastAPI route handlers (there is no OpenAPI spec to codegen from) — including a fully-traced `PretradeRiskScanResult` (risk deltas, sizing checks, exposure, correlation) sourced from `portfolio_risk_engine.py`.
  - **Dual ESM + CJS build** via tsup, with bundled `.d.ts`/`.d.cts` type declarations, targeting Node 20+.
