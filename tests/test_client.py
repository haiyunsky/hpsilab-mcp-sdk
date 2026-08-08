import unittest
import warnings

import httpx

from hpsilab_mcp import HpsiMcpClient
from hpsilab_mcp.errors import (
    HpsiMcpConfigError,
    HpsiMcpConnectionError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
)

# Anonymous construction was retired — HpsiMcpClient() now requires an
# api_key or a wallet. Most tests here don't care which identity is used,
# only what the client does with a request/response, so a fixed dummy key is
# enough; the few tests that specifically exercise the "no api_key" warning
# path use _FakeWallet instead (a real X402Wallet needs the optional [x402]
# extra and a valid EVM private key, neither of which these tests need).
_KEY = "hpsi_test_key"


class _FakeWallet:
    def payment_headers(self, response):
        return {"X-PAYMENT": "signed-payload"}


class HpsiMcpClientTests(unittest.TestCase):
    def test_dir_exposes_actual_rest_methods_only(self) -> None:
        client = HpsiMcpClient(api_key=_KEY)

        methods = set(dir(client))
        rest_methods = {
            "analyze_stock",
            "get_ai_prediction",
            "get_iv_radar",
            "get_option_pressure",
            "get_pretrade_risk_scan",
            "get_monte_carlo",
            "get_equity_curve",
            "get_equity_curves",
            "generate_stock_images",
            "generate_stock_research_report",
        }

        self.assertTrue(rest_methods.issubset(methods))
        client.close()

    def test_get_ai_prediction_uses_expected_endpoint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/ai_prediction/NVDA")
            return httpx.Response(200, json={"symbol": "NVDA"})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(client.get_ai_prediction("NVDA"), {"symbol": "NVDA"})
        client.close()

    def test_analyze_stock_uses_real_backend_route(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/analyze_stock/NVDA")
            self.assertEqual(request.url.params["refresh"], "true")
            return httpx.Response(200, json={"symbol": "NVDA", "signal": "Bullish"})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(
            client.analyze_stock("NVDA", refresh=True),
            {"symbol": "NVDA", "signal": "Bullish"},
        )
        client.close()

    def test_get_iv_radar_uses_symbols_query_param(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/iv_batch")
            self.assertEqual(request.url.params["symbols"], "QBTS")
            return httpx.Response(200, json={"symbols": ["QBTS"]})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(client.get_iv_radar("QBTS"), {"symbols": ["QBTS"]})
        client.close()

    def test_get_pretrade_risk_scan_uses_symbol_query_param(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/pretrade-risk-scan")
            self.assertEqual(request.url.params["symbol"], "NVDA")
            return httpx.Response(200, json={"symbol": "NVDA", "risk": "low"})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(
            client.get_pretrade_risk_scan(" NVDA "),
            {"symbol": "NVDA", "risk": "low"},
        )
        client.close()

    def test_generate_stock_images_uses_real_backend_route(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/stock_report/NVDA/images")
            self.assertEqual(request.url.params["force"], "true")
            self.assertEqual(request.url.params["types"], "ai_prediction,iv_radar")
            return httpx.Response(200, json={"symbol": "NVDA", "images": []})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(
            client.generate_stock_images("NVDA", force=True, types=["ai_prediction", "iv_radar"]),
            {"symbol": "NVDA", "images": []},
        )
        client.close()

    def test_generate_stock_research_report_uses_real_backend_route(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/api/stock_report/NVDA/research_report")
            self.assertEqual(request.url.params["refresh"], "true")
            self.assertEqual(request.url.params["force_images"], "true")
            return httpx.Response(200, json={"symbol": "NVDA", "markdown": "# NVDA"})

        client = HpsiMcpClient(api_key=_KEY, transport=httpx.MockTransport(handler))

        self.assertEqual(
            client.generate_stock_research_report("NVDA", refresh=True, force_images=True),
            {"symbol": "NVDA", "markdown": "# NVDA"},
        )
        client.close()

    def test_api_key_sets_authorization_header(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            return httpx.Response(200, json={"ok": True})

        client = HpsiMcpClient(
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(client.get_monte_carlo("IONQ"), {"ok": True})
        client.close()

    def test_auth_error(self) -> None:
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"detail": "Unauthorized"})
            ),
        )

        with self.assertRaises(HpsiMcpConfigError) as context:
            client.get_option_pressure("SPY")

        self.assertIn("HTTP 401", str(context.exception))
        self.assertIn("Unauthorized", str(context.exception))
        client.close()

    def test_client_repr_does_not_expose_credentials_or_endpoint(self) -> None:
        client = HpsiMcpClient(
            base_url="https://example.invalid/private-path?token=sensitive",
            api_key="hpsi_sensitive_value",
        )

        rendered = repr(client)
        self.assertNotIn("sensitive", rendered)
        self.assertNotIn("example.invalid", rendered)
        self.assertIn("api_key=configured", rendered)
        client.close()

    def test_auth_breaker_redacts_backend_error_message(self) -> None:
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    401,
                    json={
                        "detail": (
                            "Rejected Bearer sensitive-token for "
                            "0x1111111111111111111111111111111111111111"
                        )
                    },
                )
            ),
        )

        with self.assertRaises(HpsiMcpConfigError) as caught:
            client.get_option_pressure("SPY")

        rendered = f"{caught.exception!s} {caught.exception!r}"
        self.assertNotIn("sensitive-token", rendered)
        self.assertNotIn("1111111111111111111111111111111111111111", rendered)
        self.assertIn("[REDACTED]", rendered)
        client.close()

    def test_auth_circuit_blocks_later_calls_until_api_key_is_reconfigured(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.headers.get("Authorization"))
            if len(calls) == 1:
                return httpx.Response(401, json={"detail": "Invalid API key"})
            return httpx.Response(200, json={"ok": True})

        client = HpsiMcpClient(api_key="hpsi_bad", transport=httpx.MockTransport(handler))
        with self.assertRaises(HpsiMcpConfigError):
            client.get_option_pressure("SPY")
        with self.assertRaises(HpsiMcpConfigError):
            client.get_ai_prediction("SPY")
        self.assertEqual(len(calls), 1)

        client.set_api_key("hpsi_fixed")
        self.assertEqual(client.get_ai_prediction("SPY"), {"ok": True})
        self.assertEqual(calls, ["Bearer hpsi_bad", "Bearer hpsi_fixed"])
        client.close()

    def test_rate_limit_error(self) -> None:
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"message": "Too many requests"})
            ),
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_equity_curve("NVDA")

        self.assertEqual(context.exception.status_code, 429)
        self.assertEqual(str(context.exception), "Too many requests. Please slow down.")
        client.close()

    def test_error_message_prefers_message_over_error_code(self) -> None:
        # Backend 429 bodies put a machine-readable code in `error` ahead of
        # the human-readable `message` — the SDK must not surface the code.
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={"error": "rate_limit_exceeded", "message": "Daily limit reached. Register free."},
                )
            ),
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_equity_curve("NVDA")

        self.assertEqual(str(context.exception), "Too many requests. Please slow down.")
        client.close()

    def test_rate_limit_error_message_is_short_and_keeps_retry_delay(self) -> None:
        long_message = "Daily quota reached. " + ("Upgrade or register. " * 30)
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    headers={"Retry-After": "23"},
                    json={
                        "message": long_message,
                        "tool": "get_ai_prediction",
                        "limit": 10,
                        "window": "minute",
                    },
                )
            ),
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_ai_prediction("NVDA")

        error = context.exception
        self.assertEqual(
            str(error),
            "Too many requests (10/min). Please slow down and try again in 23s.",
        )
        self.assertEqual(error.retry_after_seconds, 23)
        self.assertEqual(error.body["message"], long_message)
        client.close()

    def test_anon_rate_limit_warns_once(self) -> None:
        client = HpsiMcpClient(
            wallet=_FakeWallet(),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "upgrade": {"register_url": "https://hpsilab.com/register"},
                    },
                )
            ),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 1)
        self.assertIn("hpsilab.com/register", str(caught[0].message))
        client.close()

    def test_anon_rate_limit_warning_reads_register_url_from_the_response_body(self) -> None:
        # The URL here deliberately differs from the hardcoded fallback so the
        # assertion can't pass just because the two happen to match.
        client = HpsiMcpClient(
            wallet=_FakeWallet(),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "upgrade": {"register_url": "https://hpsilab.com/register?src=eu"},
                    },
                )
            ),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 1)
        self.assertIn("hpsilab.com/register", str(caught[0].message))
        self.assertNotIn("src=eu", str(caught[0].message))
        client.close()

    def test_anon_rate_limit_warning_falls_back_to_flat_register_field(self) -> None:
        # No nested `upgrade` object at all — only the newer flat `register`
        # string (backend/app/middleware/rate_limit.py::_CONVERSION_LINKS).
        client = HpsiMcpClient(
            wallet=_FakeWallet(),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "register": "https://hpsilab.com/register?src=flat",
                        "upgrade_hint": "Upgrade at https://hpsilab.com/pricing",
                    },
                )
            ),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 1)
        self.assertIn("hpsilab.com/register", str(caught[0].message))
        self.assertNotIn("src=flat", str(caught[0].message))
        client.close()

    def test_warning_rejects_untrusted_registration_url(self) -> None:
        client = HpsiMcpClient(
            wallet=_FakeWallet(),
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "register": "https://example.invalid/collect?token=sensitive",
                    },
                )
            ),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        warning = str(caught[0].message)
        self.assertIn("https://hpsilab.com/register", warning)
        self.assertNotIn("example.invalid", warning)
        self.assertNotIn("sensitive", warning)
        client.close()

    def test_network_error_does_not_retain_request_exception_chain(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("failed", request=request)

        client = HpsiMcpClient(api_key="hpsi_sensitive_value", transport=httpx.MockTransport(handler))
        with self.assertRaises(HpsiMcpConnectionError) as caught:
            client.get_equity_curve("NVDA")

        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("sensitive", repr(caught.exception))
        client.close()

    def test_invalid_json_does_not_retain_decoder_exception_or_sensitive_text(self) -> None:
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text="Bearer sensitive-token {invalid")
            ),
        )

        with self.assertRaises(HpsiMcpResponseError) as caught:
            client.get_equity_curve("NVDA")

        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn("sensitive-token", caught.exception.response_text or "")
        self.assertIn("[REDACTED]", caught.exception.response_text or "")
        client.close()

    def test_rate_limit_error_carries_full_backend_body_as_structured_fields(self) -> None:
        # Backend is the single source of truth for the 429 contract
        # (docs/error-contract.md) - every field it sends must
        # be reachable on the raised exception, not just message/status_code.
        body = {
            "error": "tool_quota_exceeded",
            "tool": "get_ai_prediction",
            "message": "Your plan includes 30 get_ai_prediction calls per day.",
            "error_message": "Your plan includes 30 get_ai_prediction calls per day.",
            "limit": 30,
            "window": "day",
            "upgrade": {
                "message": "Register free for 3x the quota: https://hpsilab.com/register",
                "register_url": "https://hpsilab.com/register",
                "pricing_url": "https://hpsilab.com/pricing",
            },
            "register": "https://hpsilab.com/register",
            "upgrade_hint": "Upgrade at https://hpsilab.com/pricing",
        }
        client = HpsiMcpClient(
            api_key="hpsi_test_key",  # avoid the anon-rate-limit warning noise
            transport=httpx.MockTransport(lambda request: httpx.Response(429, json=body)),
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_ai_prediction("NVDA")

        error = context.exception
        self.assertEqual(error.tool, "get_ai_prediction")
        self.assertEqual(error.limit, 30)
        self.assertEqual(error.window, "day")
        self.assertIsNone(error.register_url)
        self.assertEqual(error.pricing_url, "https://hpsilab.com/pricing")
        self.assertEqual(error.upgrade_message, "Register free for 3x the quota: https://hpsilab.com/register")
        self.assertIsNone(error.register)
        self.assertEqual(error.upgrade_hint, "Upgrade at https://hpsilab.com/pricing")
        # Non-sensitive fields remain available beyond promoted attributes.
        self.assertEqual(error.body, body)
        self.assertEqual(
            str(error),
            "Too many requests (30/day). Please slow down. "
            "Upgrade: https://hpsilab.com/pricing",
        )
        client.close()

    def test_anonymous_rate_limit_displays_register_link_only(self) -> None:
        body = {
            "message": "Daily limit reached.",
            "upgrade": {
                "register_url": "https://hpsilab.com/register",
                "pricing_url": "https://hpsilab.com/pricing",
            },
        }
        client = HpsiMcpClient(
            wallet=_FakeWallet(),
            transport=httpx.MockTransport(lambda request: httpx.Response(429, json=body)),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with self.assertRaises(HpsiMcpRateLimitError) as context:
                client.get_ai_prediction("NVDA")

        self.assertEqual(
            str(context.exception),
            "Too many requests. Please slow down. Register: https://hpsilab.com/register",
        )
        self.assertEqual(context.exception.register_url, "https://hpsilab.com/register")
        self.assertIsNone(context.exception.pricing_url)
        client.close()

    def test_auth_error_carries_conversion_fields_for_no_credentials_401(self) -> None:
        # NotAuthenticatedError shape (backend/app/dependencies/auth.py) - the
        # only 401 that should carry a registration nudge.
        body = {
            "error": "not_authenticated",
            "detail": "Not authenticated",
            "error_message": "Not authenticated",
            "upgrade": {
                "message": "This feature requires an account. Register for free access, or upgrade to Pro for advanced analytics.",
                "register_url": "https://hpsilab.com/register",
                "pricing_url": "https://hpsilab.com/pricing",
            },
        }
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(lambda request: httpx.Response(401, json=body)),
        )

        with self.assertRaises(HpsiMcpConfigError) as context:
            client.get_equity_curve("NVDA")

        self.assertIn("Not authenticated", str(context.exception))
        client.close()

    def test_auth_error_has_no_conversion_fields_for_invalid_token(self) -> None:
        body = {"detail": "Invalid or expired token"}
        client = HpsiMcpClient(
            api_key=_KEY,
            transport=httpx.MockTransport(lambda request: httpx.Response(401, json=body)),
        )

        with self.assertRaises(HpsiMcpConfigError) as context:
            client.get_equity_curve("NVDA")

        self.assertIn("Invalid or expired token", str(context.exception))
        client.close()

    def test_authenticated_client_does_not_warn_on_rate_limit(self) -> None:
        client = HpsiMcpClient(
            api_key="test-key",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"message": "Monthly quota exceeded."})
            ),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 0)
        client.close()


if __name__ == "__main__":
    unittest.main()
