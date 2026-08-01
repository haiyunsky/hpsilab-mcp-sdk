import unittest
import warnings

import httpx

from hpsilab_mcp import HpsiMcpClient
from hpsilab_mcp.errors import HpsiMcpAuthError, HpsiMcpRateLimitError


class HpsiMcpClientTests(unittest.TestCase):
    def test_dir_exposes_actual_rest_methods_only(self) -> None:
        client = HpsiMcpClient()

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

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

        self.assertEqual(client.get_ai_prediction("NVDA"), {"symbol": "NVDA"})
        client.close()

    def test_analyze_stock_uses_real_backend_route(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/analyze_stock/NVDA")
            self.assertEqual(request.url.params["refresh"], "true")
            return httpx.Response(200, json={"symbol": "NVDA", "signal": "Bullish"})

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

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

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

        self.assertEqual(client.get_iv_radar("QBTS"), {"symbols": ["QBTS"]})
        client.close()

    def test_get_pretrade_risk_scan_uses_symbol_query_param(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/pretrade-risk-scan")
            self.assertEqual(request.url.params["symbol"], "NVDA")
            return httpx.Response(200, json={"symbol": "NVDA", "risk": "low"})

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

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

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

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

        client = HpsiMcpClient(transport=httpx.MockTransport(handler))

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
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"detail": "Unauthorized"})
            )
        )

        with self.assertRaises(HpsiMcpAuthError) as context:
            client.get_option_pressure("SPY")

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(str(context.exception), "Unauthorized")
        client.close()

    def test_rate_limit_error(self) -> None:
        client = HpsiMcpClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, json={"message": "Too many requests"})
            )
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_equity_curve("NVDA")

        self.assertEqual(context.exception.status_code, 429)
        self.assertEqual(str(context.exception), "Too many requests")
        client.close()

    def test_error_message_prefers_message_over_error_code(self) -> None:
        # Backend 429 bodies put a machine-readable code in `error` ahead of
        # the human-readable `message` — the SDK must not surface the code.
        client = HpsiMcpClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={"error": "rate_limit_exceeded", "message": "Daily limit reached. Register free."},
                )
            )
        )

        with self.assertRaises(HpsiMcpRateLimitError) as context:
            client.get_equity_curve("NVDA")

        self.assertEqual(str(context.exception), "Daily limit reached. Register free.")
        client.close()

    def test_anon_rate_limit_warns_once(self) -> None:
        client = HpsiMcpClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "upgrade": {"register_url": "https://hpsilab.com/register"},
                    },
                )
            )
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
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "upgrade": {"register_url": "https://hpsilab.com/register?src=eu"},
                    },
                )
            )
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 1)
        self.assertIn("hpsilab.com/register?src=eu", str(caught[0].message))
        client.close()

    def test_anon_rate_limit_warning_falls_back_to_flat_register_field(self) -> None:
        # No nested `upgrade` object at all — only the newer flat `register`
        # string (backend/app/middleware/rate_limit.py::_CONVERSION_LINKS).
        client = HpsiMcpClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    json={
                        "message": "Daily limit reached.",
                        "register": "https://hpsilab.com/register?src=flat",
                        "upgrade_hint": "Upgrade at https://hpsilab.com/pricing",
                    },
                )
            )
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with self.assertRaises(HpsiMcpRateLimitError):
                client.get_equity_curve("NVDA")

        self.assertEqual(len(caught), 1)
        self.assertIn("hpsilab.com/register?src=flat", str(caught[0].message))
        client.close()

    def test_rate_limit_error_carries_full_backend_body_as_structured_fields(self) -> None:
        # Backend is the single source of truth for the 429 contract
        # (docs/429-401-error-contract-spec.md) - every field it sends must
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
        self.assertEqual(error.register_url, "https://hpsilab.com/register")
        self.assertEqual(error.pricing_url, "https://hpsilab.com/pricing")
        self.assertEqual(error.upgrade_message, "Register free for 3x the quota: https://hpsilab.com/register")
        self.assertEqual(error.register, "https://hpsilab.com/register")
        self.assertEqual(error.upgrade_hint, "Upgrade at https://hpsilab.com/pricing")
        # Nothing lost even beyond the promoted attributes.
        self.assertEqual(error.body, body)
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
            transport=httpx.MockTransport(lambda request: httpx.Response(401, json=body))
        )

        with self.assertRaises(HpsiMcpAuthError) as context:
            client.get_equity_curve("NVDA")

        error = context.exception
        self.assertEqual(error.register_url, "https://hpsilab.com/register")
        self.assertEqual(error.pricing_url, "https://hpsilab.com/pricing")
        self.assertEqual(
            error.upgrade_message,
            "This feature requires an account. Register for free access, or upgrade to Pro for advanced analytics.",
        )
        self.assertEqual(error.body, body)
        client.close()

    def test_auth_error_has_no_conversion_fields_for_invalid_token(self) -> None:
        body = {"detail": "Invalid or expired token"}
        client = HpsiMcpClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(401, json=body))
        )

        with self.assertRaises(HpsiMcpAuthError) as context:
            client.get_equity_curve("NVDA")

        error = context.exception
        self.assertIsNone(error.register_url)
        self.assertIsNone(error.pricing_url)
        self.assertIsNone(error.upgrade_message)
        # `body` still carries the (trivial) raw response - lossless either way.
        self.assertEqual(error.body, body)
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
