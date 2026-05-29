# Changelog

All notable changes to Lumos are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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