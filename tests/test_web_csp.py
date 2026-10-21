"""Guard for the Content-Security-Policy of the web standalone bundle.

The policy pins the inline bundle by its SHA-256 hash. A rebuild that changes
the bundle without updating the hash would make the page block its own script,
and a rebuild that drops the meta tag would silently remove the protection.
"""
from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

STANDALONE = (Path(__file__).resolve().parents[1] / "web" / "v1.7.1"
              / "Lumos-v1.7.1-standalone.html")


def _policy_and_scripts() -> tuple[dict[str, list[str]], list[str]]:
    text = STANDALONE.read_bytes().decode("utf-8")
    metas = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', text)
    assert len(metas) == 1, "exactly one CSP meta tag expected"
    policy: dict[str, list[str]] = {}
    for part in metas[0].split(";"):
        name, *values = part.split()
        policy[name] = values
    bodies = [body for attrs, body in re.findall(r"<script\b([^>]*)>(.*?)</script>", text, re.S)]
    return policy, bodies


def test_inline_bundle_hash_matches_the_policy() -> None:
    policy, bodies = _policy_and_scripts()
    expected = {"'sha256-" + base64.b64encode(hashlib.sha256(b.encode("utf-8")).digest()).decode() + "'"
                for b in bodies}
    assert bodies, "no inline script found"
    assert set(policy["script-src"]) == expected


def test_policy_is_deny_by_default_and_reaches_only_the_api() -> None:
    policy, _ = _policy_and_scripts()
    assert policy["default-src"] == ["'none'"]
    assert policy["connect-src"] == ["https://api.anthropic.com"]
    for directive in ("base-uri", "form-action", "object-src"):
        assert policy[directive] == ["'none'"]
    assert "'unsafe-inline'" not in policy["script-src"]
    assert "'unsafe-eval'" not in policy["script-src"]
