"""Does what is about to be published match what is in the repository?

0.13.1 is the reason this file exists. Its artifacts were built, then the
README was corrected, then the artifacts were uploaded — so the correction
never left the repository, and PyPI carried a `PaymentPolicy` example that
told readers a wallet would cover an exhausted Credit balance. It does not.
Nothing compared the built distribution against the source, because nothing
was looking.

A wheel's `METADATA` embeds the README verbatim as the long description, and
that is what renders on the project page. Comparing the two is therefore an
exact check, not a proxy: if these differ, the page will be wrong.

The tests skip when `dist/` is empty, so an ordinary run is unaffected. They
only have an opinion once artifacts exist — which is precisely the moment
before an upload.
"""
from __future__ import annotations

import pathlib
import re
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def _wheels() -> list[pathlib.Path]:
    return sorted(DIST.glob("*.whl"))


def _metadata(wheel: pathlib.Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        return archive.read(name).decode("utf-8")


def _long_description(metadata: str) -> str:
    """Everything after the RFC 822 headers is the rendered README."""
    return metadata.split("\n\n", 1)[1] if "\n\n" in metadata else ""


def _declared_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


pytestmark = pytest.mark.skipif(not _wheels(), reason="no built distribution in dist/")


def test_the_built_readme_is_the_current_readme():
    """The check 0.13.1 did not have.

    Compared line by line rather than as one blob so a failure names the drift
    instead of just asserting two 15KB strings are unequal.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    shipped = _long_description(_metadata(_wheels()[-1])).replace("\r\n", "\n").strip()

    if readme == shipped:
        return

    only_in_repo = [l for l in readme.splitlines() if l.strip() and l not in shipped.splitlines()]
    pytest.fail(
        "dist/ was built from an older README — rebuild before publishing.\n"
        "Lines present in the repository and missing from the built artifact:\n  "
        + "\n  ".join(only_in_repo[:10])
    )


def test_the_built_version_is_the_declared_version():
    """A leftover artifact from a previous version is the other way a stale
    upload happens, and `twine upload dist/*` would take both."""
    for wheel in _wheels():
        version = re.search(r"-(\d[^-]*)-py3", wheel.name).group(1)
        assert version == _declared_version(), (
            f"{wheel.name} is not the declared version {_declared_version()} — "
            f"clear dist/ before rebuilding"
        )


def test_dist_holds_exactly_one_release():
    """`twine upload dist/*` publishes everything it finds. Two versions in
    there means one of them goes out unintentionally."""
    versions = {re.search(r"-(\d[^-]*)-py3", w.name).group(1) for w in _wheels()}

    assert len(versions) == 1, f"dist/ contains several versions: {sorted(versions)}"


def test_the_correction_that_0_13_1_shipped_without_is_in_the_artifact():
    """Specific and deliberately narrow. The general check above would catch
    this too, but a named assertion is what makes a regression legible a year
    from now — and this particular sentence is the one a reader acts on.
    """
    shipped = _long_description(_metadata(_wheels()[-1]))

    assert "A wallet does not top up an account" in shipped
    assert "api_key=API_KEY," not in shipped, (
        "the misleading PaymentPolicy example is back in the artifact"
    )
