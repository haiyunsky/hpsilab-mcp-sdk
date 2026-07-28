/**
 * Error hierarchy for @hpsilab/sdk.
 *
 * Mirrors the real Python SDK (HpsiMcpClient, github.com/haiyunsky/hpsilab-mcp-sdk)
 * 1:1 where a Python equivalent exists:
 *
 *   Python                    TypeScript
 *   ------------------------  --------------------
 *   HpsiMcpError              HPSILabError
 *   HpsiMcpConnectionError    NetworkError
 *   HpsiMcpTimeoutError       TimeoutError
 *   HpsiMcpAPIError           APIError
 *   HpsiMcpAuthError          AuthenticationError   (401 AND 403 — matches Python's
 *                                                    bucketing of "not entitled" under auth)
 *   HpsiMcpPaymentError       PaymentError          (402 — reserved for a future
 *                                                    x402-over-REST flow; the live
 *                                                    backend never returns 402 today,
 *                                                    see README "Beyond the Python SDK")
 *   HpsiMcpRateLimitError     RateLimitError        (429, carries retryAfter)
 *   HpsiMcpResponseError      ResponseError         (response body was not valid JSON)
 *   —                         ValidationError       TS-SDK-only: client-side input
 *                                                    validation (e.g. empty symbol).
 *                                                    Python raises a bare ValueError/
 *                                                    TypeError for this, not a typed
 *                                                    SDK exception.
 *
 * requestId is typed `string | undefined` on every class because the live backend
 * does not send a request-id response header today (confirmed against
 * app/middleware/request_log.py) — it is here for forward compatibility only and
 * will be undefined in practice. Never fabricate a value for it.
 */

export interface HPSILabErrorOptions {
  requestId?: string;
  rawResponse?: unknown;
  cause?: unknown;
}

/** Base class for every error this SDK throws. */
export class HPSILabError extends Error {
  readonly requestId?: string;
  readonly rawResponse?: unknown;

  constructor(message: string, options: HPSILabErrorOptions = {}) {
    super(message, options.cause !== undefined ? { cause: options.cause } : undefined);
    this.name = this.constructor.name;
    this.requestId = options.requestId;
    this.rawResponse = options.rawResponse;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** The API returned an HTTP error response (as opposed to a network/timeout failure). */
export class APIError extends HPSILabError {
  readonly status: number;

  constructor(message: string, status: number, options: HPSILabErrorOptions = {}) {
    super(message, options);
    this.status = status;
  }
}

/** 401 or 403 — matches the Python SDK, which raises HpsiMcpAuthError for both:
 * an invalid/missing token (401) and a valid token whose plan doesn't include the
 * called tool (403, e.g. get_pretrade_risk_scan on a Free-only account). */
export class AuthenticationError extends APIError {}

/** 402 Payment Required. Exported for parity with HpsiMcpPaymentError, but the
 * current REST backend never emits 402 (verified against every router — 403 for
 * "not in your plan", 429 for quota exceeded). 402 is reserved for a possible
 * future x402-over-REST flow; x402 today only exists at the MCP transport layer. */
export class PaymentError extends APIError {}

/** 429 Too Many Requests — daily/per-minute rate limit or monthly Pro-tool quota. */
export class RateLimitError extends APIError {
  /** Seconds from the `Retry-After` response header, when present. */
  readonly retryAfter?: number;
  /** Passthrough of the response body's `upgrade.register_url`, when present
   * (anon/free 429s only — omitted for developer/pro/enterprise hitting their
   * own monthly Pro-tool quota, since those callers already have an account). */
  readonly registerUrl?: string;
  /** Passthrough of the response body's `upgrade.pricing_url`, when present. */
  readonly pricingUrl?: string;

  constructor(
    message: string,
    status: number,
    options: HPSILabErrorOptions & { retryAfter?: number; registerUrl?: string; pricingUrl?: string } = {},
  ) {
    super(message, status, options);
    this.retryAfter = options.retryAfter;
    this.registerUrl = options.registerUrl;
    this.pricingUrl = options.pricingUrl;
  }
}

/** The response body could not be parsed as JSON. */
export class ResponseError extends APIError {}

/** The request failed before any HTTP response was received (DNS, TCP, TLS, abort). */
export class NetworkError extends HPSILabError {}

/** A request-level timeout. Extends NetworkError, same as Python's
 * HpsiMcpTimeoutError extending HpsiMcpConnectionError. */
export class TimeoutError extends NetworkError {}

/** Client-side input validation failure (e.g. an empty or non-string symbol).
 * Raised before any network call is made. Has no Python SDK or REST API
 * equivalent — see README "Beyond the Python SDK". */
export class ValidationError extends HPSILabError {}
