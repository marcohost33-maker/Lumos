---
name: lumos-agents-md
description: AI coding agent instructions for Lumos — a positive AI-companion shipped as a dual-lineage repo (Python `lumos` CLI package + single-file React web companion)
version: "1.1"
last_updated: 2026-05-29
priority_when_in_conflict: 1
---

# AGENTS.md — Lumos

> AI Coding Agent Instructions. Tool-agnostic format per
> [agents.md](https://agents.md/) (Linux Foundation AAIF standard, Dec 2025).
> Read by Codex, Cursor, Goose and others. Claude Code does not read AGENTS.md
> natively (issue anthropics/claude-code#6235); see `CLAUDE.md` which imports
> this file via `@AGENTS.md`. Coworkerz convention: AGENTS.md is the
> single-source-of-truth; `CLAUDE.md` is the thin import layer.

> **Priority when working agreements conflict:** lower number wins.
> §1 (working agreements) > §2 (conventions) > §3 (don't/do) > §4 (when stuck).

## Project context

- **Type:** application repository with a **dual, intentional lineage** — do not
  try to "unify" them:
  1. **Python `lumos` CLI / library** in the repo root (`src/lumos/`,
     `pyproject.toml`). A small personal assistant: reminders (NL date parsing,
     recurring daily/weekly/monthly), local SQLite storage (`~/.lumos/`, WAL),
     and Google Drive sync (narrow `drive.file` OAuth scope, backup/restore).
     This is the **primary distributable package**.
  2. **React web companion** under `web/v1.7.1/` — a single-file React
     chat/AI-companion that calls the Anthropic API directly from the browser
     (BYO API-key in `localStorage`). Distributed as **prebuilt standalone
     HTML + JSX source — there is no npm package, no `package.json`, no build
     step.** Different distribution model on purpose.
- **Purpose:** Lumos is the positive AI-companion line ("turn the lights on for
  what you need to remember / keep in sync").
- **License:** MIT.
- **Visibility:** **PUBLIC** — `marcohost33-maker/Lumos` is the *only* public
  Coworkerz repo. Treat everything here as world-readable (see §Don't).
- **KANON anchor:** `APP-LUMOS` in `Vero/Meta/KANON/KANON_APPS.yaml`.
- **Versions (dual, intentional — not a bug):** CLI `pyproject.version = 0.1.0`;
  web companion `v1.7.1`. The git-tag lineage and the package version need not
  match; do not "fix" one to the other.

## Repository layout

```
pyproject.toml              # Python package metadata (name=lumos, v0.1.0, MIT)
src/lumos/                  # PRIMARY package
  ├── __init__.py           # public API: Lumos, Reminder, DriveClient
  ├── __main__.py           # `python -m lumos`
  ├── cli.py                # `lumos` command (entry point: lumos.cli:main)
  ├── config.py             # paths & user config (~/.lumos/)
  ├── storage.py            # SQLite backend (WAL, synchronous=NORMAL)
  ├── reminders.py          # Reminder model + ReminderService
  └── drive.py              # DriveClient (Google Drive, drive.file scope)
tests/                      # pytest suite — no network required
  ├── conftest.py
  └── test_{cli,config,drive,facade,reminders,storage}.py
web/v1.7.1/                 # React companion (single-file; NO build)
  ├── Lumos-v1.7.1-standalone.html   # prebuilt bundle (~230 KB)
  ├── lumos_v1.7.1_2026-05-20.jsx    # source (~95 KB)
  ├── lumos_v1.7_2026-05-20.jsx      # predecessor source
  └── README.md
.github/workflows/
  ├── ci.yml                # PRIMARY CI — pytest on Python 3.9–3.12 (required)
  ├── encoding-guard.yml    # rejects invalid UTF-8 under .github/
  └── zizmor.yml            # workflow security audit (SHA-pinned, gates merge)
```

## Build / check commands

### Python CLI (root) — the gating suite

```bash
# install package + dev deps (matches CI)
python -m pip install --upgrade pip
pip install -e '.[dev]'          # add ,gdrive for live Google Drive work

# run the exact CI test command (must be green before merge)
pytest --cov=lumos --cov-report=term

# run the CLI
lumos status
python -m lumos --help
```

CI (`ci.yml`) runs `pytest --cov=lumos` on a **Python 3.9 / 3.10 / 3.11 / 3.12**
matrix. All four are **required status checks** on `main`.

### React web companion (`web/v1.7.1/`) — no build pipeline

```text
# There is NO npm install / build step. The companion is shipped as:
#   web/v1.7.1/Lumos-v1.7.1-standalone.html   (open directly in a browser)
#   web/v1.7.1/lumos_v1.7.1_2026-05-20.jsx     (single-file React source)
# Edit the .jsx source, regenerate the standalone HTML, bump the dated filename.
```

`encoding-guard.yml` and `zizmor.yml` only react to changes under `.github/`.

## Working agreements

1. **Branch protection: Tier-2 active.** `main` requires PR review and the four
   `pytest (Python 3.9|3.10|3.11|3.12)` checks green. No direct pushes; PRs only.
2. **PUBLIC repo — no secrets, ever.** No API keys, OAuth client secrets,
   `~/.lumos/token.json`, or personal data in code, tests, fixtures, or logs.
   The web companion is BYO-key (`localStorage`) by design — never hard-code one.
3. **Don't break the dual lineage.** The Python CLI and the React companion are
   separate deliverables with separate versions. Don't merge them, don't make
   one depend on the other, don't "sync" their version numbers.
4. **Backup-First on destructive ops.** Before any `git push --force`, branch
   delete, or ref-PATCH: capture pre-SHA via
   `gh api repos/.../git/refs/heads/...`, run the op, verify post-SHA. The
   loss-of-history incident (`liouscope_data_loss_2026_05_16`) is the cautionary
   tale.
5. **Reality-Anchor.** Prefer "pytest green on 3.9–3.12 (verified <date>)" over
   "should pass". No claims without evidence.
6. **Plain paths in code-blocks** for file references (no markdown links —
   code-block paths are clickable in CLI; markdown links are not).

## Conventions

- **Python:** package lives under `src/lumos/`; public API is re-exported from
  `__init__.py` (`Lumos`, `Reminder`, `DriveClient`). CLI is `click`-based,
  entry point `lumos.cli:main`. Keep `requires-python = ">=3.9"` compatibility.
- **Storage:** SQLite under `~/.lumos/`; preserve the WAL +
  `synchronous=NORMAL` durability/perf tradeoff.
- **Drive:** keep the narrow `drive.file` OAuth scope and the 0600 atomic
  token write; retry transient 429/5xx with exponential backoff + jitter.
  Drive deps are an **optional** extra (`gdrive`) — code must degrade gracefully
  when they're missing (tests run without network).
- **Tests:** add/extend a `tests/test_*.py` for every behaviour change; the
  suite must stay network-free (use `freezegun` / fakes, not live Drive).
- **Web companion:** edit the single-file `.jsx`, keep it CORS-legit
  (`anthropic-dangerous-direct-browser-access`), sanitize API-key input
  (ASCII-only), and bump the dated filename + `web/v1.7.1/README.md` lineage.
- **License headers:** MIT — keep `LICENSE`, `pyproject.license`, and README
  "## License" consistent on any version change.

## Don't

- Don't merge with any `pytest (Python 3.9|3.10|3.11|3.12)` check red.
- Don't merge with the `zizmor` workflow audit red.
- Don't commit secrets, OAuth tokens, `~/.lumos/token.json`, or real user data
  (PUBLIC repo).
- Don't unify, cross-couple, or version-sync the Python CLI and the React
  companion.
- Don't broaden the Google Drive scope beyond `drive.file`.
- Don't add a network dependency to the test suite.
- Don't use `--no-verify`, `--no-gpg-sign`, or `--force` without explicit
  User1 OK.

## Do

- Do run `pip install -e '.[dev]'` then `pytest --cov=lumos` locally before
  pushing.
- Do keep Drive functionality optional and gracefully degrading without the
  `gdrive` extra.
- Do update `CHANGELOG.md` and the relevant version (`pyproject.version` for the
  CLI, the dated `.jsx`/`README.md` for the web companion) on user-facing change.
- Do reference the KANON anchor (`APP-LUMOS`) when changing scope or version.
- Do keep all files under `.github/` valid UTF-8 (encoding-guard CI).

## When stuck

- See `README.md` for the CLI feature set, install, and quick-start commands.
- See `web/v1.7.1/README.md` for the React companion's lineage and security
  notes (BYO-key, sanitize, CORS).
- See `pyproject.toml` for deps, extras (`dev`, `gdrive`), and the entry point.
- **Escalate after 3 failed attempts at the same step** — stop and ask in a PR
  draft or issue instead of looping.

## Definition of Done

A change is "done" only when **all** of the following hold:

| # | Check | Exit-Code / Evidence |
|---|---|---|
| 1 | `pytest (Python 3.9)` green | required status check |
| 2 | `pytest (Python 3.10)` green | required status check |
| 3 | `pytest (Python 3.11)` green | required status check |
| 4 | `pytest (Python 3.12)` green | required status check |
| 5 | `zizmor workflow audit` passes | workflow green (gates merge) |
| 6 | `Encoding Guard` passes (if `.github/` touched) | workflow green |
| 7 | No secrets / tokens / personal data added | manual review (PUBLIC repo) |
| 8 | Dual lineage intact; versions bumped where user-facing | manual review |
| 9 | PR body contains Summary + change rationale | manual review |

A PR that misses any of 1-9 is not "ready", regardless of how reviewers feel
about the design.

---

*Tier-2 rollout 2026-05-29 (v1.1 standard). Format spec: <https://agents.md/>.*
