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


if __name__ == "__main__":
    unittest.main()
