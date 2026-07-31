# Changelog

## v0.8.0 - 2026-07-31

### Added

* **`register_account(email)` — an agent can now register its own account.**
  No password, no wallet, no web form. Returns a real `hpsi_` API key, which
  the client adopts automatically (pass `adopt_key=False` to opt out).

  The account is *also* bound to the caller server-side, so a process that
  cannot rewrite its own `Authorization` header is still recognised as that
  account on later calls. This is what the anonymous key alone could not
  solve: the key reached the model, but an MCP agent has no mechanism to send
  one back.

  The account starts unverified and keeps the anonymous daily allowance until
  the emailed link is confirmed; confirming it unlocks the full Free plan.
  Idempotent per caller — a repeat call returns the same account with a fresh
  key rather than creating a second one, so it is safe to call after losing a
  key. An address belonging to a different account raises `HpsiMcpAPIError`
  (409) and leaves the current identity untouched.

### Changed

* Payment documentation now states plainly that **a wallet is not required**:
  every 402 challenge names a card-checkout URL alongside the x402 option.

## v0.7.0 - 2026-07-30

### Added

* **Anonymous keys are now picked up automatically.** The API issues an
  un-keyed caller a free key on its first successful response; the client
  adopts it and sends it on every later request, which raises the daily
  allowance substantially. Nothing to configure.
* `HpsiMcpClient.anon_key` exposes that key, and a new `anon_key=` constructor
  argument accepts one back. Persist it between runs to keep the larger
  allowance — the key is not tied to your IP address, so it survives the
  address changes that are normal on cloud hosts.
* A `429` that ends the free anonymous pool carries the key in its body. The
  client adopts it and retries the call once, so the first time you hit the
  anonymous ceiling you get data instead of an exception.

A client constructed with a real `api_key` is unaffected: its credential is
never displaced, and no anonymous key is adopted or reported.

## v0.6.1 - 2026-07-30

### Fixed

* The `x402` extra now installs `x402[evm]` rather than bare `x402`. The EVM
  signer imports `web3` at import time and bare `x402` does not depend on it,
  so on 0.6.0 `pip install "hpsilab-mcp[x402]"` produced an install that looked
  complete but raised `ImportError` as soon as `X402Wallet(...)` was
  constructed. Existing 0.6.0 installs can be repaired with
  `pip install "x402[evm]"`.
* A failed wallet import now reports the underlying error alongside the install
  hint, instead of telling someone who already installed the extra to install
  it again.

## v0.6.0 - 2026-07-30

### Added

* **Pay-per-call (x402).** The API now answers HTTP 402 instead of a permanent
  429/403 when an anonymous caller has used up a tool's free quota (or asks for
  a Pro tool). `HpsiMcpPaymentError` carries the challenge — `accepts`, `tool`,
  `price` — so it can be paid with any x402 client. Pass
  `HpsiMcpClient(wallet=X402Wallet(private_key))`, or set
  `HPSILAB_X402_PRIVATE_KEY`, to sign and retry automatically; payments are
  capped at `max_price_usdc` (default $1.00) per call and never made
  pre-emptively. Requires the optional extra: `pip install "hpsilab-mcp[x402]"`.

### Changed

* `get_equity_curves()` is deprecated in favour of `get_equity_curve()` and now
  emits a `DeprecationWarning`; the singular name is the canonical one
  everywhere (MCP tool, REST metering, docs). The alias will be removed in the
  next major release.

## v0.5.4 - 2026-07-29

### Fixed

* `HpsiMcpAPIError.args`/`str()` no longer surfaces the backend's
  machine-readable `error` code (e.g. `"rate_limit_exceeded"`) ahead of its
  human-readable `message`/`error_message` — the friendly sentence now wins.

### Added

* Anonymous (no `api_key`) callers now get a one-time `warnings.warn()` when
  they hit a 429, pointing at `hpsilab.com/register` (or the backend's own
  `upgrade.register_url` when present) — visible even to unattended scripts
  that only check `response.status_code`. Authenticated callers never see it.

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
