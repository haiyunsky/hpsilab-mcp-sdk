# Changelog

## v0.3.0 - 2026-06-27

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
* get_equity_curves
* generate_stock_images
* generate_stock_research_report
