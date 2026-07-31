import pathlib
import re
import unittest
from unittest.mock import patch

import hpsilab_mcp

_PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _declared_version() -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', _PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert match, "no version in pyproject.toml"
    return match.group(1)


class VersionTests(unittest.TestCase):
    def test_version_is_string(self) -> None:
        self.assertIsInstance(hpsilab_mcp.__version__, str)
        self.assertTrue(hpsilab_mcp.__version__)

    def test_load_version_uses_installed_distribution(self) -> None:
        with patch("hpsilab_mcp.version", return_value="1.2.3"):
            self.assertEqual(hpsilab_mcp._load_version(), "1.2.3")

    def test_load_version_falls_back_when_not_installed(self) -> None:
        with patch("hpsilab_mcp.version", side_effect=hpsilab_mcp.PackageNotFoundError):
            self.assertEqual(hpsilab_mcp._load_version(), hpsilab_mcp._FALLBACK_VERSION)

    def test_the_fallback_still_reports_a_real_version(self) -> None:
        """A caller running from source used to report "0.0.0", which said only
        that metadata was missing. Requests carry this into `X-HPSILAB-Version`
        and the User-Agent, so a whole class of caller was unversioned in the
        logs — and therefore invisible to any before/after measurement."""
        base, _, local = hpsilab_mcp._FALLBACK_VERSION.partition("+")

        self.assertEqual(base, _declared_version())
        self.assertEqual(local, "source")

    def test_the_fallback_stays_distinguishable_from_an_installed_report(self) -> None:
        """Recovering the version must not cost the signal it replaced: a
        source checkout and an installed distribution have to stay tellable
        apart, which is the one thing "0.0.0" did well."""
        self.assertNotEqual(hpsilab_mcp._FALLBACK_VERSION, _declared_version())


if __name__ == "__main__":
    unittest.main()
