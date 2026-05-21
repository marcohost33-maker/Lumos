# Security Policy

## Reporting a vulnerability

If you find a security-relevant issue, **please do not open a public issue**.

Use GitHub's private vulnerability reporting:

1. Open the **Security** tab of this repository
2. Click **Report a vulnerability**
3. Include:
   - A description of the issue and its impact
   - Steps to reproduce
   - The affected commit SHA or release tag
   - Suggested mitigation if available

We aim to acknowledge within **7 working days** and to issue an advisory or
patch within **30 days**.

## Supported versions

Only the most recent minor version on `main` receives security fixes. There is
no LTS branch and no backport policy.

## Scope

In scope:

- Source under this repository
- CI workflows under `.github/workflows/`
- Released artifacts (when applicable)

Out of scope:

- Upstream language / library vulnerabilities — report to those projects
- Findings that require physical access to the host
- Non-security bugs (open a normal issue)

## Supply-chain hardening

This repository follows the OpenSSF recommendation to pin GitHub Actions to
a 40-character commit SHA (with a semantic-version comment). Dependency
updates are managed via Dependabot (`.github/dependabot.yml`).
