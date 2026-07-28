/**
 * Configuring retry/backoff and handling every error class. Retry and
 * ValidationError are TS-SDK-only additions with no Python SDK or REST API
 * equivalent — see README "Beyond the Python SDK".
 *
 * Run: `HPSILAB_API_KEY=hpsi_... npx tsx examples/retry-and-error-handling.ts`
 */
import {
  AuthenticationError,
  HPSILabClient,
  NetworkError,
  PaymentError,
  RateLimitError,
  ResponseError,
  TimeoutError,
  ValidationError,
} from "@hpsilab/sdk";

// Default: up to 2 retries (3 attempts total) with exponential backoff on
// 429/5xx/timeout/network errors, honoring Retry-After when the server sends one.
const defaultClient = new HPSILabClient({ apiKey: process.env.HPSILAB_API_KEY });

// Tune the retry budget explicitly.
const patientClient = new HPSILabClient({
  apiKey: process.env.HPSILAB_API_KEY,
  retries: 5,
  timeoutMs: 60_000,
});

// Fully disable retries — exactly one attempt is made, no backoff loop runs.
const noRetryClient = new HPSILabClient({
  apiKey: process.env.HPSILAB_API_KEY,
  retry: false, // equivalent to { retries: 0 }
});

async function analyze(client: HPSILabClient, symbol: string) {
  try {
    return await client.analyzeStock(symbol);
  } catch (err) {
    if (err instanceof ValidationError) {
      console.error(`Bad input, not sent over the network: ${err.message}`);
    } else if (err instanceof AuthenticationError) {
      console.error(`Auth failed (${err.status}): ${err.message}`);
    } else if (err instanceof PaymentError) {
      // Reserved for a possible future x402-over-REST flow — the current
      // REST backend never returns 402 (see README).
      console.error(`Payment required: ${err.message}`);
    } else if (err instanceof RateLimitError) {
      console.error(`Rate limited, retry after ${err.retryAfter ?? "unknown"}s: ${err.message}`);
    } else if (err instanceof ResponseError) {
      console.error(`Server sent a response we couldn't parse: ${err.message}`);
    } else if (err instanceof TimeoutError) {
      console.error(`Request timed out: ${err.message}`);
    } else if (err instanceof NetworkError) {
      console.error(`Network failure before any response: ${err.message}`);
    } else {
      throw err;
    }
    return null;
  }
}

await analyze(defaultClient, "NVDA");
await analyze(patientClient, "NVDA");
await analyze(noRetryClient, "NVDA");
