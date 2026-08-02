# HPSILab Python REST SDK

`hpsilab-mcp` is the official Python SDK for the hosted hpsilab.com REST API — quantitative finance and options analytics (IV surface, Monte Carlo simulation, AI predictions, pre-trade risk scans, and more).

> **Note:** This package wraps REST endpoints only. It does not implement MCP transport — see [MCP Transport](#mcp-transport) below if you need that.

## Requirements

- Python >= 3.9

## Installation

```bash
pip install hpsilab-mcp
```

To let the client pay per call instead of registering an account (see
[Paying without an account](#paying-without-an-account)):

```bash
pip install "hpsilab-mcp[x402]"
```

## Getting an API Key

API key is mandatory: `HpsiMcpClient()` needs either a real `api_key` or a
configured `wallet=` to even construct — there is no more anonymous free
access (see [Paying without an account](#paying-without-an-account) if you'd
rather skip a key entirely). Two ways to get one, pick whichever fits:

**Path A — you (a human) already have, or want, a hpsilab.com account.**

1. Sign up / log in at <https://hpsilab.com/register>.
2. Go to **Settings → API Keys** and generate one (prefix `hpsi_`).
3. Pass it as `api_key=` — done, skip to [Quick Start](#quick-start) below.

**Path B — an agent/script with no human sign-up step, or you just want it
from code.** No password, no browser, no web form — one function call:

```python
import hpsilab_mcp

result = hpsilab_mcp.register(email="you@example.com")
print(result["api_key"])   # 'hpsi_...' — save this, it's shown once
```

1. `hpsilab_mcp.register(email=...)` — no client instance needed, this is the
   one thing that works before you have any identity at all.
2. The response's `api_key` is a real, usable key immediately — pass it to
   `HpsiMcpClient(api_key=...)` and start calling tools right away.
3. The account starts **unverified**, which caps you at the anon-rate daily
   allowance rather than the full Free plan. Click the link in the
   verification email (or relay it to the human you're working with) to
   unlock the full plan — see
   [Registering your own account](#registering-your-own-account-for-agents)
   below for the full detail (idempotent re-calls, lost-email recovery,
   binding an unattended caller to the account it registered).

Either path ends the same way: a real `hpsi_` key you pass as `api_key=`.
There's no difference in what the key can do — Path A just goes through the
website first, Path B skips it.

## Quick Start

Path B end-to-end — register, then call a tool:

```python
import hpsilab_mcp
from hpsilab_mcp import HpsiMcpClient

result = hpsilab_mcp.register(email="you@example.com")
client = HpsiMcpClient(api_key=result["api_key"])

calls = {
    "analyze_stock": client.analyze_stock("NVDA"),
    "get_ai_prediction": client.get_ai_prediction("NVDA"),
    "get_iv_radar": client.get_iv_radar("NVDA"),
    "get_option_pressure": client.get_option_pressure("NVDA"),
    "get_pretrade_risk_scan": client.get_pretrade_risk_scan("NVDA"),
    "get_monte_carlo": client.get_monte_carlo("NVDA"),
    "get_equity_curve": client.get_equity_curve("NVDA"),
    "generate_stock_images": client.generate_stock_images("NVDA"),
    "generate_stock_research_report": client.generate_stock_research_report("NVDA"),
}

print(calls["analyze_stock"])
```

## Authentication

Every REST SDK method requires either a real account (`api_key=`) or a
configured x402 `wallet=` (see [Paying without an
account](#paying-without-an-account) below) — the SDK enforces this at
construction time, before any request goes out, rather than letting an
unauthenticated call reach the API and fail there.

```python
from hpsilab_mcp import HpsiMcpClient

client = HpsiMcpClient(
    api_key="YOUR_API_KEY",
    base_url="https://hpsilab.com",
)

result = client.get_ai_prediction("TSLA")
print(result)
```

### Reading a 429/401 without re-parsing JSON

A `429` (rate limit / quota exceeded) raises `HpsiMcpRateLimitError` with the
backend's fields promoted onto it — no need to parse `response_text` yourself:

```python
from hpsilab_mcp import HpsiMcpRateLimitError

try:
    client.get_ai_prediction("NVDA")
except HpsiMcpRateLimitError as exc:
    print(exc.tool, exc.limit, exc.window)     # get_ai_prediction 30 day
    print(exc.register_url, exc.pricing_url)   # where to register / upgrade
    print(exc.body)                            # the full raw response, if needed
```

`HpsiMcpAuthError` (401/403) carries the same `register_url`/`pricing_url`/
`upgrade_message` — but only when the 401 means "no credentials sent at all".
An expired token, or a 403, leaves all three `None`: you already have an
account, so the SDK does not suggest registering one.

## Registering your own account (for agents)

No client instance needed — this is the entry point for a caller that has
neither an `api_key` nor a wallet yet. No password, no web form:

```python
import hpsilab_mcp
from hpsilab_mcp import HpsiMcpClient

result = hpsilab_mcp.register(email="you@example.com")
print(result["api_key"])

client = HpsiMcpClient(api_key=result["api_key"])
client.get_monte_carlo("NVDA")     # now metered as your account
```

The account is *also* bound to this caller server-side — so a process that
cannot change its own `Authorization` header (an MCP connection, for
instance) is still recognised on later calls made from the same caller.

The account starts unverified, which keeps the anon-rate daily allowance
until the emailed link is confirmed; confirming it unlocks the full Free
plan. Use a real address — one nobody reads leaves the account at that lower
allowance forever.

Calling `hpsilab_mcp.register()` again with the same email returns the same
account and a fresh key rather than creating a second one, so it is safe to
call when you have lost your key. An address that already belongs to a
different account raises `HpsiMcpAPIError` with status `409`.

Already have a client constructed (typically wallet-only, via `wallet=`) and
want it to also have an account? `HpsiMcpClient.register_account(email)` is
the same registration, as an instance method — it switches the client over to
the new key automatically. Pass `adopt_key=False` to get the response without
switching, e.g. to hand the key to another process instead.

### Lost the verification email?

An unverified account stays on the anon-rate daily allowance — not the full
Free plan — until the link in that email is confirmed. If the email never
arrived or the link expired, request a new one instead of registering again:

```python
client.resend_verification_email()
```

Requires a real account key (`api_key=`, or whatever `register_account()`
just adopted) — a wallet-only client, or one with an invalid/expired key, gets
`HpsiMcpAuthError` instead: there's no more fingerprint-based fallback for a
header-less caller (API key is mandatory now, and fingerprint binding was
itself a no-key-needed identity — closed along with the rest of anonymous
access). The backend also enforces a short cooldown between resends; calling
it again too soon raises `HpsiMcpRateLimitError`.

## Paying without an account

Calling a tool with no `api_key` — a `wallet=` alone is enough to construct a
client — the API answers **HTTP 402** with an [x402](https://x402.org)
payment challenge instead of refusing outright, so an agent can pay for the
call in USDC on Base and keep working without ever registering.

**You do not need a wallet either**, if you'd rather register instead — see
[Registering your own account](#registering-your-own-account-for-agents)
above; it needs no wallet and no browser, and resolves this within the
running process. Every 402 challenge also names a card checkout URL
(`https://hpsilab.com/pricing?anon=...`) for a human to pay with a card
instead, if neither a wallet nor unattended registration fits.

Without a wallet the SDK raises `HpsiMcpPaymentError` with the challenge
attached, and you can pay it however you like:

```python
from hpsilab_mcp import HpsiMcpClient, HpsiMcpPaymentError

try:
    client.get_monte_carlo("NVDA")
except HpsiMcpPaymentError as exc:
    print(exc.tool, exc.price)   # get_monte_carlo $0.10
    print(exc.accepts)           # scheme / network / asset / amount / payTo
```

With a wallet, the client signs the challenge and repeats the request for you:

```python
from hpsilab_mcp import HpsiMcpClient, X402Wallet

client = HpsiMcpClient(wallet=X402Wallet(PRIVATE_KEY, max_price_usdc=0.20))
client.get_monte_carlo("NVDA")   # no account needed — paid per call
```

`X402Wallet()` reads `HPSILAB_X402_PRIVATE_KEY` when no key is passed, and a
client with no `wallet=` picks that variable up automatically (an `api_key=`
still satisfies construction on its own either way — a wallet is only
required when there's no `api_key`). Three things hold regardless of how it
is configured:

* Nothing is paid pre-emptively — the call is always attempted first, and
  only pays if the response comes back 402.
* Each call is retried **once** after paying; a server that keeps answering
  402 cannot drain the wallet.
* `max_price_usdc` (default `$1.00`) caps a single call. A challenge asking for
  more is refused, not signed.

Signing happens locally; the private key never leaves your process.

| Tool | Price per call |
| --- | ---: |
| `analyze_stock`, `get_pretrade_risk_scan` | $0.15 |
| `get_monte_carlo` | $0.10 |
| `get_iv_radar`, `get_option_pressure`, `get_ai_prediction`, `get_equity_curve` | $0.05 |
| `generate_stock_research_report` | $0.35 |

## Version

```python
import hpsilab_mcp

print(hpsilab_mcp.__version__)
```

## Request tracking

Every request carries `X-HPSILAB-Source: sdk`, `X-HPSILAB-Client: python-sdk`,
`X-HPSILAB-Version: <installed version>`, `X-HPSILAB-Tool: <method name>` (e.g.
`get_ai_prediction`), and `User-Agent: hpsilab-python-sdk/<version>`. These are
merged into any custom `headers` you pass to `HpsiMcpClient(...)` without
overriding `Authorization` or other business headers.

## REST SDK Methods

| Method | Endpoint |
| --- | --- |
| `analyze_stock(symbol)` | `GET /api/analyze_stock/{symbol}` |
| `get_ai_prediction(symbol)` | `GET /api/ai_prediction/{symbol}` |
| `get_iv_radar(symbol)` | `GET /api/iv_batch?symbols={symbol}` |
| `get_option_pressure(symbol)` | `GET /api/option_pressure/{symbol}` |
| `get_pretrade_risk_scan(symbol)` | `GET /api/pretrade-risk-scan?symbol={symbol}` |
| `get_monte_carlo(symbol)` | `GET /api/monte_carlo/{symbol}` |
| `get_equity_curve(symbol)` | `GET /api/equity_curve/{symbol}` |
| `get_equity_curves(symbol)` | Deprecated alias of `get_equity_curve` — warns on use |
| `generate_stock_images(symbol)` | `POST /api/stock_report/{symbol}/images` |
| `generate_stock_research_report(symbol)` | `POST /api/stock_report/{symbol}/research_report` |

The SDK itself does not publish MCP tool annotations; those are declared by the
MCP server in its `tools/list` response. The `GET` analysis methods are
read-only. The two `generate_*` methods create or refresh hosted artifacts and
may consume quota or trigger payment; repeated calls are not guaranteed to be
idempotent.

## Capability Matrix

| Capability | REST API | MCP |
| --- | --- | --- |
| `analyze_stock` | Yes | Yes |
| `get_ai_prediction` | Yes | Yes |
| `get_iv_radar` | Yes | Yes |
| `get_option_pressure` | Yes | Yes |
| `get_pretrade_risk_scan` | Yes | Yes |
| `get_monte_carlo` | Yes | Yes |
| `get_equity_curve` | Yes | Yes |
| `generate_stock_images` | Yes | Yes |
| `generate_stock_research_report` | Yes | Yes |

## MCP Transport

All official MCP tools have REST SDK coverage. Use an MCP-compatible client (e.g. Claude, or any MCP host) when you specifically need MCP transport, tool discovery, or assistant-native tool calls — see the [MCP server docs](https://hpsilab.com/developer/v2) for setup.

## Scope

This package is a REST API wrapper only. It does not implement MCP transport, SSE, streaming, tool discovery, Claude integration, or proprietary finance logic.

These tools return research-oriented information. **They are not financial advice.**

## Links

- [Homepage](https://hpsilab.com)
- [Developer Portal](https://hpsilab.com/developer/v2)
- [Repository](https://github.com/haiyunsky/hpsilab-mcp-sdk)

## License

MIT. See `LICENSE`.
