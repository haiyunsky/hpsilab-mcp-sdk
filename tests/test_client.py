import unittest

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


if __name__ == "__main__":
    unittest.main()
