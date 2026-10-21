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


@pytest.mark.parametrize("filename", ["lumos_v1.7.1_2026-05-20.jsx", "Lumos-v1.7.1-standalone.html"])
def test_api_key_is_never_written_to_local_storage(filename: str) -> None:
    text, name = _source_and_name(filename)
    writes = re.findall(r"localStorage\.setItem\(\s*" + re.escape(name) + r"\s*,", text)
    assert writes == [], f"{filename}: API key written to localStorage"


@pytest.mark.parametrize("filename", ["lumos_v1.7.1_2026-05-20.jsx", "Lumos-v1.7.1-standalone.html"])
def test_api_key_is_kept_in_session_storage_and_legacy_copy_removed(filename: str) -> None:
    text, name = _source_and_name(filename)
    assert re.search(r"sessionStorage\.setItem\(\s*" + re.escape(name) + r"\s*,", text)
    assert re.search(r"localStorage\.removeItem\(\s*" + re.escape(name) + r"\s*\)", text)
