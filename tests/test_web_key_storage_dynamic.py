"""Run the web companion's key-storage functions against fake Web Storage objects.

The regex guard in test_web_key_storage.py proves where the key may be written, not what
the functions do on each path. This test extracts loadApiKey/saveApiKey (and the sanitizer
they call) from the JSX sources and the minified bundle and executes them in Node with
storages that can hold, refuse or throw. Browser-only semantics (a second local file in the
same tab, sessionStorage copied into a popup) are out of reach here; web/v1.7.1/README.md
lists them as residual risks.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_web_key_storage import FILES, _source_and_name

NODE = shutil.which("node")


def _function_bodies(text: str) -> dict[str, str]:
    """Map every top-level `function NAME(...) {...}` to its full source text."""
    out: dict[str, str] = {}
    for m in re.finditer(r"function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", text):
        depth, i, quote = 0, m.end() - 1, None
        while i < len(text):
            c = text[i]
            if quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = None
            elif c in "'\"`":
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    out.setdefault(m.group(1), text[m.start():i + 1])
                    break
            i += 1
    return out


def _storage_functions(filename: str) -> tuple[str, str, str, str]:
    text, name = _source_and_name(filename)
    bodies = _function_bodies(text)
    load = [n for n, b in bodies.items() if f"sessionStorage.getItem({name})" in b]
    save = [n for n, b in bodies.items() if f"sessionStorage.removeItem({name})" in b]
    assert len(load) == 1 and len(save) == 1, (filename, load, save)
    helpers = sorted(
        n for n in bodies
        if n not in (load[0], save[0])
        and re.search(r"(?<![\w$.])" + re.escape(n) + r"\(", bodies[load[0]] + bodies[save[0]])
    )
    prelude = f"const {name} = 'lumos.apikey.v1';\n" + "\n".join(bodies[h] for h in helpers)
    return prelude, bodies[load[0]], bodies[save[0]], f"{load[0]}|{save[0]}"


HARNESS = r"""
const K = 'lumos.apikey.v1';
function store(init, fail) {
  const m = new Map(Object.entries(init));
  return {
    getItem(k) { if (fail.get) throw new Error('SecurityError'); return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { if (fail.set) throw new Error('QuotaExceededError'); m.set(k, String(v)); },
    removeItem(k) { if (fail.remove) throw new Error('SecurityError'); m.delete(k); },
    dump() { return m.has(K) ? m.get(K) : null; },
  };
}
function run(c) {
  const S = c.session === undefined ? undefined : store(c.session, c.sessionFail || {});
  const L = store(c.local || {}, c.localFail || {});
  if (S === undefined) delete globalThis.sessionStorage; else globalThis.sessionStorage = S;
  globalThis.localStorage = L;
  for (const k of c.save || []) SAVE(k);
  const loaded = LOAD();
  return { loaded, session: S ? S.dump() : null, local: L.dump() };
}
const out = {};
for (const [id, c] of Object.entries(CASES)) out[id] = run(c);
process.stdout.write(JSON.stringify(out));
"""

# id: (case, expected {loaded, session, local})
CASES = {
    "legacy_only": ({"session": {}, "local": {"lumos.apikey.v1": "sk-L"}},
                    {"loaded": "sk-L", "session": "sk-L", "local": None}),
    "session_only": ({"session": {"lumos.apikey.v1": "sk-S"}, "local": {}},
                     {"loaded": "sk-S", "session": "sk-S", "local": None}),
    "session_and_legacy": ({"session": {"lumos.apikey.v1": "sk-S"},
                            "local": {"lumos.apikey.v1": "sk-L"}},
                           {"loaded": "sk-S", "session": "sk-S", "local": None}),
    "empty_session_value": ({"session": {"lumos.apikey.v1": ""},
                             "local": {"lumos.apikey.v1": "sk-L"}},
                            {"loaded": "sk-L", "session": "sk-L", "local": None}),
    "local_access_throws": ({"session": {"lumos.apikey.v1": "sk-S"}, "local": {},
                             "localFail": {"get": True}},
                            {"loaded": "sk-S", "session": "sk-S", "local": None}),
    # Codex P2 on 12a41b5: the legacy copy was already gone when setItem threw.
    "session_refuses_copy": ({"session": {}, "local": {"lumos.apikey.v1": "sk-L"},
                              "sessionFail": {"set": True}},
                             {"loaded": "sk-L", "session": None, "local": None}),
    "session_read_throws": ({"session": {}, "local": {"lumos.apikey.v1": "sk-L"},
                             "sessionFail": {"get": True}},
                            {"loaded": "sk-L", "session": "sk-L", "local": None}),
    "no_session_storage": ({"local": {"lumos.apikey.v1": "sk-L"}},
                           {"loaded": "sk-L", "session": None, "local": None}),
    "save_then_reload": ({"session": {}, "local": {}, "save": ["sk-new"]},
                         {"loaded": "sk-new", "session": "sk-new", "local": None}),
    "save_empty_clears": ({"session": {"lumos.apikey.v1": "sk-S"}, "local": {},
                           "save": [""]},
                          {"loaded": "", "session": None, "local": None}),
}


@pytest.mark.skipif(NODE is None, reason="node not on PATH (GitHub ubuntu runners ship it)")
@pytest.mark.parametrize("filename", FILES)
def test_key_storage_paths_execute_as_documented(filename: str) -> None:
    prelude, load, save, names = _storage_functions(filename)
    load_name, save_name = names.split("|")
    program = "\n".join([
        prelude, load, save,
        f"const LOAD = {load_name}; const SAVE = {save_name};",
        "const CASES = " + json.dumps({k: v[0] for k, v in CASES.items()}) + ";",
        HARNESS,
    ])
    proc = subprocess.run([NODE, "-e", program], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    wrong = {k: (got[k], v[1]) for k, v in CASES.items() if got[k] != v[1]}
    assert not wrong, f"{filename}: (got, expected) {wrong}"
