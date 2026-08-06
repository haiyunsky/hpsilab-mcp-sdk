# Upgrading hpsilab-mcp

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
