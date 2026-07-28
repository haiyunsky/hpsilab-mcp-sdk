import { describe, expect, it } from "vitest";
import {
  APIError,
  AuthenticationError,
  HPSILabError,
  NetworkError,
  PaymentError,
  RateLimitError,
  ResponseError,
  TimeoutError,
  ValidationError,
} from "../src/errors";

describe("error hierarchy", () => {
  it("chains APIError subclasses through HPSILabError", () => {
    const err = new AuthenticationError("nope", 401);
    expect(err).toBeInstanceOf(AuthenticationError);
    expect(err).toBeInstanceOf(APIError);
    expect(err).toBeInstanceOf(HPSILabError);
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("AuthenticationError");
    expect(err.status).toBe(401);
  });

  it("chains PaymentError, RateLimitError, ResponseError through APIError", () => {
    expect(new PaymentError("x", 402)).toBeInstanceOf(APIError);
    expect(new RateLimitError("x", 429)).toBeInstanceOf(APIError);
    expect(new ResponseError("x", 200)).toBeInstanceOf(APIError);
  });

  it("chains TimeoutError through NetworkError, not APIError", () => {
    const err = new TimeoutError("timed out");
    expect(err).toBeInstanceOf(NetworkError);
    expect(err).toBeInstanceOf(HPSILabError);
    expect(err).not.toBeInstanceOf(APIError);
  });

  it("keeps ValidationError separate from the HTTP-error branch", () => {
    const err = new ValidationError("bad input");
    expect(err).toBeInstanceOf(HPSILabError);
    expect(err).not.toBeInstanceOf(APIError);
    expect(err).not.toBeInstanceOf(NetworkError);
  });

  it("carries retryAfter on RateLimitError when provided", () => {
    const err = new RateLimitError("slow down", 429, { retryAfter: 30 });
    expect(err.retryAfter).toBe(30);
  });

  it("defaults requestId to undefined and never fabricates one", () => {
    const err = new APIError("x", 500);
    expect(err.requestId).toBeUndefined();
  });

  it("preserves rawResponse for debugging", () => {
    const err = new APIError("x", 500, { rawResponse: { detail: "boom" } });
    expect(err.rawResponse).toEqual({ detail: "boom" });
  });
});
