# Changelog

All notable changes to Lumos are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Tests are timezone-independent on every OS. The `_set_tz` fixture relied on
  `TZ` + `time.tzset()`, which does not exist on Windows, so five reminder tests failed on
  any non-UTC Windows machine (measured: Europe/Zurich, 2 h offset). `lumos.reminders`
  now resolves the local zone through `LOCAL_TZ` / `_as_local()`; `None` (the default)
  is exactly the previous `astimezone()` behaviour, and the fixture pins it to UTC.

### Security
- Web companion: the API key lives in `sessionStorage` only (ends with the tab). A key left in
  `localStorage` by an earlier version is moved into the session once and removed, and removed
  on every later load too, even when the session already holds a key. Measured in Chromium under
  `file://`: another local HTML file in a new tab no longer reads the key (before: it did).
  `tests/test_web_key_storage.py` guards both JSX sources and the bundle (any `setItem` of the key
  must go to `sessionStorage`, no index write); CSP hash re-pinned.
- Web companion: a storage error no longer loses the key. If the session refuses the copied
  legacy key (quota, `SecurityError`), the key still serves the page from memory; if reading
  `localStorage` throws, a valid session key is kept (before: both returned an empty key); an
  empty session value takes the legacy key. `tests/test_web_key_storage_dynamic.py` executes
  the storage functions of both JSX sources and the minified bundle in Node against fake
  storages (ten paths; five of them fail on the previous code). The source is renamed to
  `lumos_v1.7.1_2026-10-22.jsx` (dated-filename convention).
- Web companion: browser gate for the key storage. `tests/test_web_key_storage_browser.py` loads
  the shipped bundle in Chromium under `file://` (network blocked) and watches the key three ways:
  a spy on `Storage.prototype`, a second tab that receives every `localStorage` `storage` event
  (index writes included), and a scan of the final contents. Ten cases (legacy/session/both/empty
  seeds, either storage denied, key entered in the settings dialog, empty save, new tab and
  `noopener` popup, residual risks). Measured: 10/10 on this bundle, 9/10 fail on the bundle from
  before the session-only change; four write mutants (computed name, computed alias,
  `Storage.prototype.setItem.call`, index write) all fail it, while the static guard catches only
  the index write. New CI job `web-browser` (Playwright hash-pinned in
  `requirements-web-browser.txt`, `LUMOS_REQUIRE_BROWSER=1` so it cannot skip); the four required
  pytest jobs skip the test.
- Web companion: hash-based Content-Security-Policy in `Lumos-v1.7.1-standalone.html`
  (`default-src 'none'`, script by SHA-256, `connect-src https://api.anthropic.com` only).
  Measured in Chrome: renders with no violation; foreign `fetch`, image beacon and injected
  inline script are blocked. `tests/test_web_csp.py` guards hash and directives.
- Web companion README documents the residual risks, including a measured one: Chrome shares
  `localStorage` across all `file://` pages, so a stored key is readable by any other local
  HTML file.

## [1.7.2] - 2026-05-28

CI/Security hardening pass — no user-facing change.

### Security
- `zizmor` workflow security audit added (SHA-pinned `zizmorcore/zizmor-action@v0.5.6`).
- Dependabot config with 7-day cooldown against supply-chain attacks (Shai-Hulud counter, May 2026).
- All GitHub Actions SHA-pinned (actions/checkout @11bd7190... v4.2.2).
- `codeql-action` upgraded from v3.35.5 to v4.36.0.
- UTF-8 encoding guard workflow added.
- `.gitattributes` with `eol=lf` normalization.

### Tier-2.5 Branch Protection (repo-level)
- `enforce_admins=true`, `required_conversation_resolution=true`, `dismiss_stale_reviews=true` (solo-dev pattern, `required_approving_review_count=0`).
- `delete_branch_on_merge=true`.

## [1.7.1] - earlier baseline

Previous: Streaming + Prompt-Editor + Retry-Backoff + Token-Usage tracking.
See git history for full detail; this file starts tracking at v1.7.2.