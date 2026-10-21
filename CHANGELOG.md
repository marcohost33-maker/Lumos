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
  `localStorage` by an earlier version is moved into the session once and removed. Measured in
  Chromium under `file://`: another local HTML file in a new tab no longer reads the key (before:
  it did). `tests/test_web_key_storage.py` guards JSX and bundle; CSP hash re-pinned.
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