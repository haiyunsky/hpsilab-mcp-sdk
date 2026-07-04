import unittest
from unittest.mock import patch

import hpsilab_mcp


class VersionTests(unittest.TestCase):
    def test_version_is_string(self) -> None:
        self.assertIsInstance(hpsilab_mcp.__version__, str)
        self.assertTrue(hpsilab_mcp.__version__)

    def test_load_version_uses_installed_distribution(self) -> None:
        with patch("hpsilab_mcp.version", return_value="1.2.3"):
            self.assertEqual(hpsilab_mcp._load_version(), "1.2.3")

    def test_load_version_falls_back_when_not_installed(self) -> None:
        with patch("hpsilab_mcp.version", side_effect=hpsilab_mcp.PackageNotFoundError):
            self.assertEqual(hpsilab_mcp._load_version(), "0.0.0")


if __name__ == "__main__":
    unittest.main()
