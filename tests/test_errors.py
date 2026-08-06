import unittest

from hpsilab_mcp.errors import (
    HpsiMcpAPIError,
    HpsiMcpAuthError,
    HpsiMcpConnectionError,
    HpsiMcpError,
    HpsiMcpRateLimitError,
    HpsiMcpResponseError,
    HpsiMcpTimeoutError,
)


class ErrorTests(unittest.TestCase):
    def test_error_hierarchy(self) -> None:
        self.assertTrue(issubclass(HpsiMcpAPIError, HpsiMcpError))
        self.assertTrue(issubclass(HpsiMcpAuthError, HpsiMcpAPIError))
        self.assertTrue(issubclass(HpsiMcpRateLimitError, HpsiMcpAPIError))
        self.assertTrue(issubclass(HpsiMcpResponseError, HpsiMcpAPIError))
        self.assertTrue(issubclass(HpsiMcpConnectionError, HpsiMcpError))
        self.assertTrue(issubclass(HpsiMcpTimeoutError, HpsiMcpConnectionError))

    def test_api_error_stores_response_context(self) -> None:
        error = HpsiMcpAPIError(
            "Request failed.",
            status_code=500,
            response_text='{"detail":"failed"}',
        )

        self.assertEqual(str(error), "Request failed.")
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.response_text, '{"detail":"failed"}')

    def test_api_error_redacts_sensitive_response_context(self) -> None:
        error = HpsiMcpAPIError(
            "Rejected credential hpsi_sensitive_value and wallet 0x1111111111111111111111111111111111111111.",
            status_code=401,
            response_text='{"authorization":"Bearer sensitive-token","private_key":"secret"}',
            body={
                "authorization": "Bearer sensitive-token",
                "nested": {
                    "api_key": "hpsi_sensitive_value",
                    "payTo": "0x1111111111111111111111111111111111111111",
                },
            },
        )

        serialized = f"{error!s} {error!r} {error.response_text!r} {error.body!r}"
        self.assertNotIn("sensitive", serialized)
        self.assertNotIn('"secret"', serialized)
        self.assertNotIn("1111111111111111111111111111111111111111", serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
