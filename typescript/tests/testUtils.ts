import { vi } from "vitest";
import type { FetchLike } from "../src/config";

export interface MockResponseInit {
  status: number;
  headers?: Record<string, string>;
  /** JSON-serializable body. Ignored if `bodyText` is set. */
  body?: unknown;
  /** Raw response body text — use to simulate malformed JSON. */
  bodyText?: string;
}

export function mockResponse(init: MockResponseInit): Response {
  const bodyText = init.bodyText ?? (init.body !== undefined ? JSON.stringify(init.body) : "");
  return new Response(bodyText, {
    status: init.status,
    headers: init.headers,
  });
}

export interface RecordedCall {
  url: string;
  method: string | undefined;
  headers: Record<string, string>;
}

/** A fetch mock that returns one Response per call, in order (the last entry
 * repeats once the list is exhausted), and records every call it received. */
export function sequenceFetch(responses: Response[]): { fetch: FetchLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  let index = 0;
  const fetchFn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((value, key) => {
      headers[key] = value;
    });
    calls.push({ url, method: init?.method, headers });

    const response = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (!response) {
      throw new Error("sequenceFetch: no mock response configured");
    }
    return response;
  });
  return { fetch: fetchFn as unknown as FetchLike, calls };
}

/** A fetch mock that rejects with a TypeError, simulating a network failure
 * before any response was received (DNS/TCP/TLS failure). */
export function networkErrorFetch(): { fetch: FetchLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const fetchFn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: input.toString(), method: init?.method, headers: {} });
    throw new TypeError("fetch failed");
  });
  return { fetch: fetchFn as unknown as FetchLike, calls };
}

/** A fetch mock that never resolves on its own — only rejects with
 * AbortError once the caller's AbortSignal fires, simulating a hung request
 * that the client's own timeout must cut off. */
export function hangingFetch(): { fetch: FetchLike; calls: RecordedCall[] } {
  const calls: RecordedCall[] = [];
  const fetchFn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: input.toString(), method: init?.method, headers: {} });
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("The operation was aborted.", "AbortError"));
      });
    });
  });
  return { fetch: fetchFn as unknown as FetchLike, calls };
}
