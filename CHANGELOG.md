# Changelog

## v0.5.3 - 2026-07-23

### Added

* API tracking headers on every request: `X-HPSILAB-Source`,
  `X-HPSILAB-Client`, `X-HPSILAB-Version`, and `X-HPSILAB-Tool` (per method
  called), plus a `hpsilab-python-sdk/<version>` `User-Agent`. Merged on top
  of any custom `headers` without overriding `Authorization`.

### Documentation

* Clarified that MCP tool annotations are server-side metadata and that the two
  `generate_*` SDK methods create or refresh hosted artifacts, may consume
  quota or trigger payment, and are not guaranteed to be idempotent.

## v0.5.1 - 2026-07-05

### Improved

* Refined package metadata for PyPI discoverability: updated `description`
  to clearly state this is a REST API SDK for quantitative finance and
  options analytics.
* Expanded `keywords` to include `options-analytics`, `implied-volatility`,
  `monte-carlo`, `black-scholes`, `stock-analytics`.
* Added `classifiers` for development status, audience, topic, supported
  Python versions (3.9–3.12), and OS independence.

## v0.5.0 - 2026-07-04

### Changed

* Removed the client-side Pro-tool guard (`_guard_pro` / `PRO_TOOLS`
  allowlist). Previously, calling a Pro method (`get_ai_prediction`,
  `get_equity_curve`, `generate_stock_images`,
  `generate_stock_research_report`) without an API key raised
  `HpsiMcpPaymentError` immediately, with no network call. Now the request
  is always sent, and `HpsiMcpPaymentError` is raised only after the
  backend responds with HTTP 402 — the backend is the sole source of truth
  for tier enforcement, avoiding client/server allowlist drift.
* README: added a note that all listed SDK methods are callable without an
  API key and that the SDK does not block any method client-side; renamed
  "Authenticated Usage" section to "Optional Authenticated Usage".

<!-- Note: HpsiMcpPaymentError itself is unchanged and still raised on a
     real 402 response; only the pre-flight client-side check was removed. -->

## v0.4.0 - 2026-07-04

### Added

* `get_pretrade_risk_scan(symbol)` — `GET /api/pretrade-risk-scan?symbol={symbol}`

## v0.3.0 - 2026-06-26

### Added

* Tiered access support: Free, Freemium, and Pro tools now work consistently
  across MCP, REST API, and SDK.
* `HpsiMcpPaymentError` (HTTP 402) — raised when a Pro tool is called without a
  paid plan. Exported from the package root.

### Improved

* No API key → anonymous read-only mode: the client sends the
  `x-mcp-anonymous-readonly` header (no bogus Bearer), so Free + Freemium tools
  work without an account.
* Pro tools now fail fast client-side (no wasted round-trip) with a clear
  upgrade message when called without an API key.

<!-- Note: this fail-fast behavior was removed again in v0.5.0 above. -->

## v0.2.0 - 2026-06-22

### Added

* analyze_stock()
* generate_stock_images()
* generate_stock_research_report()

### Improved

* Full parity across MCP, REST API, and Python SDK
* Updated README examples
* Added complete 8-tool Quick Start

### Official Tool Set

* analyze_stock
* get_ai_prediction
* get_iv_radar
* get_option_pressure
* get_monte_carlo
* get_pretrade_risk_scan
* get_equity_curves
* generate_stock_images
* generate_stock_research_report

<!-- Note: get_pretrade_risk_scan is listed here as part of the planned
     tool set, but the SDK method itself wasn't actually added until
     v0.4.0 (confirmed via wheel diff) — likely available via MCP/REST
     before the SDK wrapper caught up. -->
