# Changelog

## v0.11.0 - 2026-08-03

### Breaking

* **`HpsiMcpClient()` now requires `api_key=` or `wallet=`.** Anonymous free
  access was retired backend-side — API key is mandatory on the MCP/SDK
  channel, with x402 payment as the one remaining key-free path. Constructing
  a client with neither now raises `HpsiMcpConfigError` immediately, before
  any request is sent, instead of silently running in a now-nonexistent
  anonymous mode.
* **Removed**: the `anon_key=` constructor parameter, the `client.anon_key`
  property, and all automatic anonymous-key adoption (`_adopt_anon_key`, the
  429 adopt-and-retry behavior). The backend never issues an anonymous key to
  this channel anymore, so there was nothing left for this to adopt.

### Added

* **`hpsilab_mcp.register(email, base_url=..., transport=...)`** — a
  standalone module-level function for a caller with no client instance yet
  (construction itself now requires an identity, so there had to be a
  key-free way to bootstrap one). Wraps the same `POST /api/agent/register`
  `client.register_account()` uses.

### Migration

```python
# Before
client = HpsiMcpClient()  # ran anonymously

# After — get a free key first, no client instance needed
result = hpsilab_mcp.register(email="you@example.com")
client = HpsiMcpClient(api_key=result["api_key"])

# Or pay per call instead, without ever registering
client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY))
```

## v0.10.1 - 2026-08-01

### Changed

* **`resend_verification_email()`'s docstring and the README now match what
  the backend actually does.** A quantum_app-side fix shipped after v0.10.0
  made `POST /api/auth/resend-verification` also resolve a caller with **no
  token at all** via the same fingerprint lookup `register_account()` uses —
  the docs here still said a real account key was required and an anonymous
  caller would get `HpsiMcpAuthError`. No code change on this side; the SDK
  already just posts to the endpoint and lets the backend decide. Purely
  catching the docs up to backend behavior that moved out from under them.

## v0.10.0 - 2026-08-01

### Added

* **`client.resend_verification_email()`** — for a caller already holding a
  real (bound but unverified) account key. A bound-but-unverified account's
  daily pool stays at the anonymous rate until the email is confirmed, and
  the 429 that reports this now points here instead of
  `https://hpsilab.com/settings` — that page has no resend-verification
  feature (API key / watchlist / subscription only), a dead end for a script
  with no browser session. This wraps `POST /api/auth/resend-verification`,
  which takes a bearer token, so it's reachable from a running process.
  Raises `HpsiMcpRateLimitError` if you already requested one recently (the
  backend enforces a short cooldown).

## v0.9.0 - 2026-08-01

### Added

* **`HpsiMcpRateLimitError` and `HpsiMcpAuthError` now carry the backend's
  full 429/401 response as structured attributes**, not just `message`/
  `status_code`/`response_text`. Backend is the single source of truth for
  the 429/401 contract (see quantum_app's
  `docs/429-401-error-contract-spec.md`); this SDK layer promotes it into
  attributes instead of making every caller re-parse `response_text` JSON by
  hand.

  * `HpsiMcpRateLimitError`: `tool`, `limit`, `window`, `register_url`,
    `pricing_url`, `upgrade_message`, and the backend's original flat
    `register`/`upgrade_hint` strings.
  * `HpsiMcpAuthError`: `register_url`, `pricing_url`, `upgrade_message` — all
    three are `None` for anything other than a 401 with no credentials sent
    at all (an expired token, or a 403, never carries a registration nudge —
    that is intentional, not a gap).
  * Both, plus every other `HpsiMcpAPIError` subclass, gain `.body` — the
    parsed response, verbatim — so a field not promoted to a named attribute
    is still reachable without a future SDK release, mirroring the existing
    `HpsiMcpPaymentError.accepts`/`.tool`/`.price` pattern.

```python
try:
    client.get_ai_prediction("NVDA")
except HpsiMcpRateLimitError as exc:
    print(exc.tool, exc.limit, exc.window)   # get_ai_prediction 10 day
    print(exc.register_url, exc.pricing_url) # https://hpsilab.com/register ...
```

## v0.8.2 - 2026-07-31

### Changed

* **The 429/402 anonymous-quota warnings are now one unified message**,
  matching the same simplification made on the backend and mcp_server
  (`_SIMPLE_QUOTA_MESSAGE`): "Free API key required. Register at
  `https://hpsilab.com/register`, or call
  `client.register_account(email=...)`." Replaces the separate keyed/unkeyed
  wording (`_warn_anon_rate_limited` no longer treats a caller already
  holding an anonymous key differently) and drops the per-call price from
  the 402 warning text — the price is still on the raised
  `HpsiMcpPaymentError`, it just isn't repeated here.

## v0.8.1 - 2026-07-31

### Fixed

* **A 402 no longer silences the only prompt an anonymous caller gets.**
  `_raise_for_status` branches on 402 before 429, so crossing from "rate
  limited" into "free quota exhausted" used to *switch off* the
  `warnings.warn` nudge — the one thing on this path a human actually reads.
  A caller's second session therefore produced a bare `HpsiMcpPaymentError`
  traceback recommending a crypto wallet, and nothing else. 402 now warns the
  same way 429 does.

* `HpsiMcpPaymentError`'s message and both rate-limit warnings now lead with
  `client.register_account(email=...)` rather than a URL or a wallet. It is
  the only option here that a running process can take on its own: no wallet,
  no browser, no second person. The wallet and the signup URL still follow.

* **Running from source reports a real version again.** With no installed
  distribution to read, `__version__` fell back to `"0.0.0"` — which reached
  the API in `X-HPSILAB-Version` and the User-Agent, leaving vendored-source
  callers unversioned in the logs. The fallback is now `"<version>+source"`,
  which keeps that case distinguishable without throwing the version away.

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
