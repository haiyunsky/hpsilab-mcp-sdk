# Changelog

## v0.13.11 - 2026-08-11

- Added an instance-local 60-second `insufficient_credits` circuit breaker.
  The existing request lock now covers breaker check, backend request, and
  breaker update atomically, so concurrent calls on one client send at most
  one request after the balance is known to be empty. x402 challenges and
  settlement behavior are unchanged. Call
  `clear_insufficient_credits_circuit()` after a top-up to recheck immediately.

## v0.13.10 - 2026-08-10

- Reject missing, blank, and malformed registration email addresses locally in
  both registration entry points, before any HTTP request. Validation failures
  expose `email_required` / `invalid_email`, `retryable=true`,
  `next_action=provide_email`, and `credits_charged=0`.

## v0.13.9 - 2026-08-10

### Changed

* Expanded the README examples with practical exception handling for account
  registration, authenticated requests, verification-email resends, rate
  limits, and x402 payments.
* Documented `HpsiMcpSettlementUnknownError` separately from ordinary payment
  failures so callers do not automatically retry a payment whose settlement
  outcome is unknown.

## v0.13.8 - 2026-08-10

### Changed

* Corrected `HpsiMcpPaymentError` rejection details: `insufficient_funds`
  remains an explicit empty-wallet reason, while `invalid_payload` now retains
  the safe clarification that the facilitator could not validate the signed
  payload and therefore did not confirm the wallet balance. Arbitrary
  facilitator exception text is still excluded from the public exception.
  Registration and plan guidance stays in the account/payment flows where
  caller identity and payment context are known.
* Updated the README, API reference, and upgrading guide to document the
  compact public message and the structured, redacted diagnostic fields.

## v0.13.5 - 2026-08-08

### Changed

* `HpsiMcpRateLimitError` now has a compact, stable display message while
  retaining the redacted response context and structured limit fields. When
  available it includes the limit and retry delay, for example:
  `Too many requests (10/min). Please slow down and try again in 34s.`
* Conversion links are identity-aware: anonymous clients receive only the
  registration link, while API-key Free clients receive only the paid upgrade
  link. Links are restricted to the public `hpsilab.com/register` and
  `hpsilab.com/pricing` endpoints.
* Server-supplied long-form explanations no longer expand the exception text;
  recursively redacted details remain available through typed attributes and
  `body` for callers that need them.
* Facilitator payment rejections are similarly compact in tracebacks, for
  example `Payment rejected: invalid_payload.`; redacted diagnostics remain in
  the exception's structured response context.

## v0.13.4 - 2026-08-08

The client's half of "never pay twice for one call". The API's half shipped
first: an unresolved settlement now comes back as `settlement_status:
"unknown"` with a `call_id` and no offer, and its ledger is unique on that id.
None of that holds if the client walks away and starts over — a fresh request
gets a fresh id, a fresh challenge and a fresh signature, and pays again for
work that may already have been paid for.

### Added

* **`HpsiMcpSettlementUnknownError`**, raised when the API says a payment may
  have completed and could not be confirmed. It carries `call_id`, `tool` and
  `settlement_status`.

  It is deliberately **not** a subclass of `HpsiMcpAPIError`, unlike every
  other error this SDK raises for an API response. `except HpsiMcpAPIError:
  retry()` is the most ordinary line a caller writes, and for this one response
  it is the line that costs money — so the error is placed where that handler
  cannot catch it. It is meant to be loud. Crashing is cheaper than paying
  twice.

  Nothing can have depended on the previous behaviour: this response shape did
  not exist before today.

* **`X-Request-Id` on every request**, one id per logical call, shared by the
  unpaid attempt and the paid retry. This is what makes the API's
  uniqueness constraint apply to a *retry* rather than only to a replay of the
  same signed payment — without it the API mints a fresh id per HTTP request,
  and a caller that retried a paid call defeated the constraint built to stop
  exactly that. An `X-Request-Id` pinned in the constructor's `headers=` no
  longer reaches the wire, since one id shared by every call would make the
  second paid call collide with the first.

* **`unresolved_settlements` in `payment_spend_summary()`** — `{call_id: tool}`
  for every call whose payment outcome is unknown, including the pre-existing
  timeout and dropped-connection cases, which stopped the client paying but
  never recorded *which* calls were at stake. The record survives
  `set_wallet()`: reopening the x402 path after reconciliation is a repair, and
  forgetting the evidence is not part of it.

### Changed

* An unresolved settlement closes the x402 path for that client, the same as a
  paid retry that times out. Credits-funded calls keep working — nothing about
  the API key failed. `client.set_wallet(wallet)` reopens it once
  reconciliation has said what happened.

## v0.13.3 - 2026-08-08

Two payment defects, both found by auditing the flow before the first real
settlement rather than after it. Both could cost money; neither raised
anything.

### Fixed

* **The client paid the dearest acceptable offer, not the cheapest.** With a
  challenge listing $0.90 and $0.05 — both under a $1.00
  `max_payment_per_call` — it paid $0.90. Every offer under the ceiling passes
  every check equally, so taking the first one handed whoever writes the
  challenge a lever: order `accepts` dearest-first and the caller spends the
  most their policy allows, with the cap doing its job the whole time. Offers
  are now sorted by amount, so ordering cannot change what is paid.

  This costs you nothing: a ceiling is permission to spend *at most* that
  much, never an instruction to spend it.

* **The policy and the wallet chose an offer independently and nothing
  compared them.** `PaymentPolicy` picks one from `accepts`; `X402Wallet`
  hands the whole response to the x402 client, which picks again; the
  signature commits to the wallet's choice. A multi-offer challenge could be
  approved at one price and signed at another — with the budget charged for
  the approved one, which is the quiet version of that failure.

  `X402Wallet.sign()` now returns the signed payload alongside the headers,
  and the client compares `PaymentPayload.accepted` against the approved offer
  on amount, asset and network before the retry is sent. A mismatch closes the
  x402 path and charges nothing.

### Added

* `X402Wallet.sign(response)` → `(headers, agreed)`. `payment_headers()` is
  unchanged and still works; a custom wallet without `sign()` still pays, but
  its choice cannot be checked, which the client treats as *unverifiable*
  rather than as fine.

## v0.13.2 - 2026-08-08

Documentation only, and it exists because 0.13.1 shipped one correction short.

### Fixed (documentation)

* **The `PaymentPolicy` example showed `api_key=` and `wallet=` on the same
  client, which reads as "pay per call when the Credits run out". It does not
  do that — in that configuration the wallet is never reached at all.**

  The reason is server-side. The API does not offer x402 to a caller it can
  identify: a signed-in request over its plan gets `402 insufficient_credits`,
  a 402 with no `accepts`, so `PaymentPolicy` has nothing to authorise and
  `HpsiMcpInsufficientCreditsError` is raised. Buying Credits and paying per
  call are separate doors, and a key means you are already through the first.

  The example is keyless now, the rule is stated beside it, and two tests hold
  it — one contrasting the same policy and wallet with and without a key, and
  one that fails if the API ever *does* start offering payment to keyed
  callers, so this section gets rewritten at that moment rather than quietly
  going stale.

  This correction was written before 0.13.1 was published but after its
  artifacts were built, and nothing compared the two. `tests/test_release.py`
  now does: it fails if a built distribution in `dist/` carries a README older
  than the repository's.

## v0.13.1 - 2026-08-08

Documentation only. No code changed since 0.13.0 — `src/` is byte-identical,
so upgrading is safe and changes nothing at runtime.

### Fixed (documentation)

* **The `PaymentPolicy` example showed `api_key=` and `wallet=` together, as
  if the wallet were a fallback for an exhausted Credit balance. It is not —
  in that configuration the wallet is never used at all.** The API does not
  offer x402 to a caller it can identify: a signed-in request over its plan
  gets `402 insufficient_credits`, which carries no payment offer, so
  `PaymentPolicy` has nothing to authorise and `HpsiMcpInsufficientCreditsError`
  is raised. Buying Credits and paying per call are separate doors. The
  example is now keyless, with the rule stated next to it and two tests
  holding it — including one that fails if the API ever starts offering
  payment to keyed callers, so the docs get corrected then rather than years
  later.

* **The pricing table implied every priced tool could be bought with a wallet.
  Three of them cannot.** Pay-per-call is an allowlist on the server side, and
  `analyze_stock` (a composite whose partial fan-out failure has no refund
  path) and `generate_stock_research_report` (creates a hosted artifact an
  on-chain settlement cannot un-create) are off it. They still show a price,
  because that is what they cost in Credits — a wallet simply cannot spend it.
  The table now has a "Payable with a wallet" column.

  Nothing in the SDK needed changing for this: a tool that cannot be bought
  never produces a settleable offer, so `PaymentPolicy` never authorises a
  payment and `HpsiMcpPaymentError` already reports that no offer arrived.
* `get_equity_curve` is now payable, at **$0.07** rather than $0.05. It was
  held off the allowlist because $0.05 for 6 Credits worked out below the
  Developer plan's per-Credit rate — the one tool where paying per call beat
  subscribing.
* Corrected the 0.12.2 entry, which claimed `.gitignore` was excluded from
  release artifacts. It is excluded from the wheel and **cannot** be excluded
  from the sdist: hatchling force-includes VCS exclusion files there and no
  build setting overrides it. The wheel — what `pip install` uses — is clean.

## v0.13.0 - 2026-08-08

### Breaking

* A wallet found in `HPSILAB_X402_PRIVATE_KEY` no longer authorises payment on
  a client that also has an `api_key`. Holding a key is not consent to spend
  it, and an environment variable is ambient — frequently left over from
  another project. Such a client now stays on Credits and raises
  `HpsiMcpPaymentError` on a payment challenge. Pass
  `payment_mode="x402_fallback"` to restore the previous behaviour. A wallet
  passed to the constructor, and an environment wallet on a client with no
  `api_key`, both still authorise payment.
* A `402` returned *after* a payment was made now closes only the x402 path
  rather than the whole client's authentication circuit, and raises
  `HpsiMcpPaymentError` instead of `HpsiMcpConfigError`. A server that will
  not accept a valid payment is not a bad credential; Credits-funded calls on
  the same client keep working. The wallet-drain guard is unchanged — one
  signature per logical call, then the x402 path shuts.
* A wallet that cannot sign a challenge likewise closes the x402 path and
  raises `HpsiMcpPaymentError`, where it previously raised
  `HpsiMcpConfigError`.

### Added

* `PaymentPolicy` — the spending rules, separate from the wallet that carries
  them out: `mode` (`credits_only` by default), `max_payment_per_call`,
  `max_payment_per_session`, `max_payment_per_day`, `allowed_payment_assets`,
  `allowed_networks`, `x402_allowed_tools`. Passed as `payment_policy=`, or
  `payment_mode=` for the shorthand. Ceilings are `Decimal` and validated at
  construction.
* `client.payment_spend_summary()` — what has been spent this session and
  today, against which ceilings, plus why the x402 path is closed if it is.
* `client.set_payment_policy()` — replaces the rules without refunding spend
  already recorded.

### Changed

* An offer in an asset whose decimals this SDK does not know is refused rather
  than signed. An amount is an integer in the asset's base units, so reading
  150000 units of an 18-decimal token as USDC turns $0.15 into $150,000.
* A paid retry that times out or loses its connection is counted as spent and
  closes the x402 path. Whether the authorization settled is unknowable from
  the client, and a second signature for the same logical call is the one
  outcome that must not follow.
* `HpsiMcpPaymentError` now explains a policy refusal in its message, so
  "the server offered nothing payable" and "your own policy said no" are
  distinguishable.
* `client.set_wallet()` reopens the x402 path but no longer changes the
  payment mode — repairing a wallet must not promote a `credits_only` client
  into one that spends.

## v0.12.2 - 2026-08-06

### Security

* Redact API keys, authorization values, private-key fields, payment
  signatures, mnemonic fields, and wallet-shaped values from exception
  messages and stored response context.
* Disconnect transport exceptions from their underlying `httpx.Request` so
  structured exception collectors cannot recover request headers.
* Remove wallet addresses from `X402Wallet.__repr__()` and replace private-key
  parser failures with a fixed, unchained error.
* Accept only public `https://hpsilab.com` registration links in warnings and
  remove query strings and fragments before display.
* Exclude repository-only `CHANGELOG.md` from release artifacts, and
  `.gitignore` from the wheel. The sdist still carries `.gitignore`:
  hatchling force-includes VCS exclusion files there and no build setting
  overrides it. The wheel, which is what `pip install` uses, is clean.

## v0.12.1 - 2026-08-06

### Breaking

* HTTP `401` and unresolved HTTP `402` now raise `HpsiMcpConfigError` and
  open the current Client's authentication circuit. Code catching
  `HpsiMcpAuthError` or `HpsiMcpPaymentError` for those statuses must migrate
  to `HpsiMcpConfigError`. HTTP `403` still raises `HpsiMcpAuthError`.

### Changed

* Added a per-client authentication circuit breaker. The first unresolved
  HTTP 401 or 402 raises `HpsiMcpConfigError`; subsequent calls on that client
  fail locally until `set_api_key()` or `set_wallet()` is called. A 402 is
  retried only once and only when a configured wallet can sign the challenge.
* Shortened every `HpsiMcpConfigError` to a developer-focused three-part
  format: summary, reason, and recovery steps.
* Reduced published artifacts. Wheel and sdist exclude `tests/`, `docs/`,
  `examples/`, `python/`, and `typescript/`; the repository keeps them for
  development and reference.

### Migration

```python
from hpsilab_mcp import HpsiMcpConfigError

try:
    result = client.get_monte_carlo("NVDA")
except HpsiMcpConfigError:
    # Retrying before reconfiguration is blocked locally.
    client.set_api_key("NEW_API_KEY")
```

`client.set_wallet(X402Wallet(PRIVATE_KEY))` or a new Client are the other
recovery paths. Removing the Client's only authentication method is rejected.

## v0.11.2 - 2026-08-03

### Changed

* **Simplified the "Getting an API Key" section** — v0.11.1 added it as two
  fully-numbered 3-4 step paths with a closing summary paragraph; cut down to
  a two-bullet list (website vs. code) since that's all either path actually
  needs, with a pointer to "Registering your own account" for anyone who
  wants the detail (verification, lost-key recovery, idempotency). No code
  change.

## v0.11.1 - 2026-08-03

### Changed

* **README: added a "Getting an API Key" section** laying out both ways to get
  one as an explicit numbered flow — generating one from the website
  (`hpsilab.com` → Settings → API Keys) for a human who already has or wants
  an account, and `hpsilab_mcp.register(email=...)` for an agent/script with
  no sign-up step. v0.11.0 added the `register()` function itself and
  mentioned it in passing; this makes both paths to a key the first thing a
  new reader sees, right after Installation. No code change.

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
