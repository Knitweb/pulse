"""Cross-repo version-drift guard: knitweb (this repo) vs molgang's pinned range.

molgang runs on this engine and pins it in its ``pyproject.toml`` as
``knitweb>=X.Y,<A.B``. This test fails when the installed ``knitweb`` drifts
outside that range — a different major, an older-than-floor version, or a
version at/above molgang's ceiling — so a silent incompatibility is caught in CI
before either repo ships (issue #277). It is meant to gate both sides.

molgang's ``pyproject.toml`` is read from ``$MOLGANG_PYPROJECT`` when set
(molgang's own CI points at its local checkout); otherwise it is fetched from
GitHub. If it cannot be obtained (e.g. the runner is offline), the test
*skips* rather than flaking — set ``MOLGANG_PYPROJECT`` to gate deterministically.
"""

from __future__ import annotations

import os
import re
import tomllib
import urllib.request

import pytest

import knitweb

MOLGANG_PYPROJECT_RAW = "https://raw.githubusercontent.com/Knitweb/molgang/main/pyproject.toml"


def _version_tuple(v: str) -> tuple[int, int, int]:
    core = re.split(r"[-+]", str(v), maxsplit=1)[0]
    parts = (core.split(".") + ["0", "0", "0"])[:3]
    try:
        return tuple(int(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        pytest.skip(f"unparseable version: {v!r}")


def _molgang_pyproject_text() -> str:
    local = os.environ.get("MOLGANG_PYPROJECT")
    if local:
        if not os.path.exists(local):
            pytest.skip(f"MOLGANG_PYPROJECT points at a missing file: {local}")
        return open(local, encoding="utf-8").read()
    try:
        with urllib.request.urlopen(MOLGANG_PYPROJECT_RAW, timeout=10) as r:
            return r.read().decode("utf-8")
    except Exception as e:  # offline / rate-limited → skip, don't flake
        pytest.skip(f"molgang pyproject unavailable ({e}); set MOLGANG_PYPROJECT to gate offline")


def _molgang_knitweb_pin() -> str:
    data = tomllib.loads(_molgang_pyproject_text())
    for dep in data.get("project", {}).get("dependencies", []):
        if re.match(r"\s*knitweb\b", dep):
            return dep.strip()
    pytest.skip("molgang does not depend on knitweb in [project].dependencies")


def _bounds(pin: str) -> tuple[tuple | None, tuple | None]:
    floor = re.search(r">=\s*([0-9][0-9.]*)", pin)
    ceil = re.search(r"<\s*([0-9][0-9.]*)", pin)
    return (_version_tuple(floor.group(1)) if floor else None,
            _version_tuple(ceil.group(1)) if ceil else None)


def test_knitweb_within_molgang_pin():
    kw = _version_tuple(knitweb.__version__)
    pin = _molgang_knitweb_pin()
    floor, ceil = _bounds(pin)

    if floor is not None:
        assert kw[0] == floor[0], (
            f"knitweb major drift: engine is {knitweb.__version__} but molgang pins "
            f"'{pin}' (major {floor[0]}). Hold the engine major or bump molgang's range."
        )
        assert kw >= floor, (
            f"knitweb {knitweb.__version__} is older than molgang's floor in '{pin}'. "
            f"molgang expects at least {'.'.join(map(str, floor))}."
        )
    if ceil is not None:
        assert kw < ceil, (
            f"knitweb version drift: engine is {knitweb.__version__}, at/above molgang's "
            f"ceiling in '{pin}'. molgang will reject this engine — widen molgang's knitweb "
            f"range (and engine_compat) before releasing this version, or hold it back."
        )
