# Upgrading hpsilab-mcp

## v0.14.0: the free allowance is no longer a payment error

Affects anyone calling without an API key, and any account whose email is not
yet verified.

The API answers HTTP 402 with `error: "anonymous_allowance_exhausted"` when the
free evaluation allowance for unidentified callers is spent. Until now this SDK
did not recognise the code and raised `HpsiMcpPaymentError` for it, with
`accepts` and `price` both `None` — a message telling a caller who owes nothing
to configure a wallet. It now raises `HpsiMcpAllowanceExhaustedError`.

```python
from hpsilab_mcp import HpsiMcpAllowanceExhaustedError

try:
    client.get_monte_carlo("NVDA")
except HpsiMcpAllowanceExhaustedError as exc:
    # Free and immediate: no password, no wallet, no web form. On a client that
    # already exists, this also binds the account to the caller server-side.
    client.register_account(email="you@example.com")
```

`except HpsiMcpPaymentError` no longer catches this case. That is the breaking
part, and it is the point: paying does not lift this ceiling, so a handler that
paid was never going to succeed. Keep catching `HpsiMcpPaymentError` for real
x402 offers, which are unchanged.

The exception carries `calls_used`, `calls_allowed`, `calls_allowed_next`,
`window_days`, and `next_actions` — the API's own remedies, cheapest first.
Prefer acting on `next_actions` over parsing the message: for a caller with no
account its first entry is `register_account`, and for an account whose email
is unverified it is `verify_email` instead, which is a distinction this client
does not have to make itself.

## v0.13.14: structured rate-limit upgrade guidance

`HpsiMcpRateLimitError` now promotes the HTTP 429 fields
`upgrade_available`, `upgrade_message`, and `upgrade_url` to typed attributes.
The URL is restricted to the trusted public HPSILab pricing endpoint before it
is exposed or included in `str(exc)`.

Existing integrations using `pricing_url` remain compatible: for a response
that supplies only `upgrade_url`, `pricing_url` resolves to the same validated
URL. Prefer `upgrade_available` to decide whether to show an upgrade action and
`upgrade_url` as its destination. Retry behavior is unchanged; a 429 does not
open the authentication or Credits circuit breakers.

## v0.13.8: accurate payment rejection contract

`HpsiMcpPaymentError` again distinguishes an empty wallet
(`Payment rejected: insufficient_funds.`) from an `invalid_payload`, where the
facilitator did not validate the signed payload and therefore did not confirm
the balance. It does not embed registration or pricing instructions. Use
`accepts`, `tool`, `price`, and the recursively redacted `body` for structured
handling; registration and plan selection continue through their existing
account/payment flows.

## v0.13.5: compact, identity-aware rate-limit errors

`str(HpsiMcpRateLimitError)` is now a short stable sentence instead of the
backend's complete quota and conversion copy. Code should continue reading
`retry_after_seconds`, `limit`, `window`, `tool`, and the recursively redacted
`body` attributes when it needs structured details.

Anonymous clients receive a registration URL; API-key Free clients receive a
pricing/upgrade URL. A caller that parsed conversion URLs out of the old error
sentence should switch to `register_url` or `pricing_url`.

## v0.13.4: unresolved settlements are not API errors

Only affects clients that pay with a wallet. If you use an API key alone,
nothing here applies.

The API can now answer that a payment may have completed and it cannot confirm
which — `settlement_status: "unknown"`, with a `call_id` and **no** offer. The
SDK raises `HpsiMcpSettlementUnknownError` for it, outside the
`HpsiMcpAPIError` branch of the hierarchy.

That placement is the migration. A blanket handler no longer covers this case:

```python
# Before — this caught everything the API could raise
try:
    data = client.get_iv_radar("NVDA")
except HpsiMcpAPIError:
    retry()

# After — the unresolved case escapes it, on purpose
try:
    data = client.get_iv_radar("NVDA")
except HpsiMcpSettlementUnknownError as exc:
    log.error("payment outcome unknown, call_id=%s", exc.call_id)   # do not retry
except HpsiMcpAPIError:
    retry()
```

Leaving your code unchanged is safe in the money sense — the error propagates
instead of being retried, and the client stops paying regardless. It will
simply reach your caller as an unhandled exception. Catch `HpsiMcpError` if
you want one handler for everything this SDK raises.

**Do not retry the call, and do not pay for it again.** Record `exc.call_id`
and reconcile; a retry signs a new authorization for work that may already be
paid for.

| Situation | Result |
|---|---|
| API answers `settlement_status: "unknown"` | Raise `HpsiMcpSettlementUnknownError`; close the x402 path |
| Paid retry times out / connection drops | Unchanged, and now recorded with a `call_id` |
| Any other 5xx | Continue raising `HpsiMcpAPIError` |
| Credits-funded calls afterwards | Continue working |
| Reopening payments | `client.set_wallet(wallet)`, after reconciliation |

Every request now also carries an `X-Request-Id` — one per logical call, shared
by the unpaid attempt and the paid retry, so the API's settlement ledger can
enforce one settlement per call. If you pinned `headers={"X-Request-Id": ...}`
when constructing the client, it no longer reaches the wire: a single id shared
by every call would make the second paid call collide with the first.

## v0.12.1: authentication circuit breaker

This release changes how the Python SDK handles HTTP `401` and `402`.
Previously, repeatedly calling a misconfigured Client could send a new invalid
request each time. The Client now remembers the first unresolved authentication
or payment failure and blocks subsequent calls locally.

Configuration errors now use a compact summary/reason/fix layout. Creating a
Client without an API Key or Wallet produces:

```text
HpsiMcpConfigError: API key or wallet required.

Anonymous access has ended.

Free API key:
    hpsilab_mcp.register(email="you@example.com")

Or configure:
    api_key=
    wallet=
    HPSILAB_X402_PRIVATE_KEY
```

### Behavior changes

| Situation | Result |
|---|---|
| First HTTP 401 | Raise `HpsiMcpConfigError` and open the circuit |
| Later call on that Client | Raise locally; send no HTTP request |
| HTTP 402 without a Wallet | Do not retry; raise `HpsiMcpConfigError` |
| HTTP 402 with a usable Wallet | Sign and retry once |
| Paid retry still returns 402 | Raise `HpsiMcpConfigError` and open the circuit |
| Wallet cannot sign | Do not retry; raise `HpsiMcpConfigError` |
| HTTP 403 | Continue raising `HpsiMcpAuthError`; no circuit |
| HTTP 429 | Continue raising `HpsiMcpRateLimitError`; no circuit |

The transition is protected by an instance lock, so concurrent calls sharing
one Client cannot continue sending requests after the circuit opens.

### Required exception migration

Before:

```python
from hpsilab_mcp import HpsiMcpAuthError, HpsiMcpPaymentError

try:
    result = client.get_monte_carlo("NVDA")
except (HpsiMcpAuthError, HpsiMcpPaymentError) as exc:
    print(exc)
```

After:

```python
from hpsilab_mcp import HpsiMcpConfigError

try:
    result = client.get_monte_carlo("NVDA")
except HpsiMcpConfigError as exc:
    print(exc)
    # Do not retry until this Client is reconfigured.
```

### Recovering the same Client

Replace the API Key:

```python
client.set_api_key("NEW_API_KEY")
result = client.get_monte_carlo("NVDA")
```

Or configure an x402 Wallet:

```python
from hpsilab_mcp import X402Wallet

client.set_wallet(X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
result = client.get_monte_carlo("NVDA")
```

Both methods reset the circuit. Creating a new `HpsiMcpClient` also starts
with a closed circuit. `set_api_key(None)` is rejected when no Wallet exists,
and `set_wallet(None)` is rejected when no API Key exists.

### x402 retry policy

The SDK never retries a `402` unless a configured Wallet successfully creates
payment headers. It never pays pre-emptively and performs at most one paid
retry per call. Third-party wallet exceptions are deliberately suppressed
from the public traceback so signed payment context cannot leak into logs.

See [the authentication circuit-breaker test plan](auth-circuit-breaker-test-plan.md)
for executable validation steps and acceptance criteria.

### Published package contents

The `0.12.1` Wheel contains only the importable `hpsilab_mcp` package and
standard `.dist-info` metadata. The sdist contains the package source plus
the required build metadata and top-level README, changelog, and license.
Development-only `tests/`, `docs/`, `examples/`, `python/`, and `typescript/`
directories are no longer included in either artifact.
