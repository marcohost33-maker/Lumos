"""Guard: the web companion keeps the API key in sessionStorage, never in localStorage.

Under file:// Chrome shares localStorage across all local pages, so a persisted key is
readable by any other local HTML file (measured 2026-10-16, web/v1.7.1/README.md).
The bundle is minified, so the key's storage name is resolved from its literal.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web" / "v1.7.1"
KEY_LITERAL = "lumos.apikey.v1"


def _source_and_name(filename: str) -> tuple[str, str]:
    text = (WEB / filename).read_bytes().decode("utf-8")
    m = re.search(r"\b([A-Za-z_$][\w$]*)\s*=\s*['`\"]" + re.escape(KEY_LITERAL) + r"['`\"]", text)
    assert m, f"storage name for {KEY_LITERAL} not found in {filename}"
    return text, m.group(1)


FILES = ["lumos_v1.7.1_2026-10-22.jsx", "lumos_v1.7_2026-05-20.jsx", "Lumos-v1.7.1-standalone.html"]


@pytest.mark.parametrize("filename", FILES)
def test_api_key_is_never_written_to_local_storage(filename: str) -> None:
    # Every write of the key must go to sessionStorage by name: an alias such as
    # `S.setItem(name, v)` or an index write `localStorage[name] = v` would slip
    # past a check that only looks for `localStorage.setItem`.
    text, name = _source_and_name(filename)
    n = re.escape(name)
    receivers = re.findall(r"([A-Za-z_$][\w$.]*)\.setItem\(\s*" + n + r"\s*,", text)
    assert receivers, f"{filename}: no write of the API key found"
    assert set(receivers) == {"sessionStorage"}, f"{filename}: key written via {sorted(set(receivers))}"
    assert not re.search(r"\[\s*" + n + r"\s*\]\s*=(?!=)", text), f"{filename}: index write of the key"


@pytest.mark.parametrize("filename", FILES)
def test_api_key_is_kept_in_session_storage_and_legacy_copy_removed(filename: str) -> None:
    text, name = _source_and_name(filename)
    assert re.search(r"sessionStorage\.setItem\(\s*" + re.escape(name) + r"\s*,", text)
    assert re.search(r"localStorage\.removeItem\(\s*" + re.escape(name) + r"\s*\)", text)
