# Contributing to Lumos

Thanks for your interest in Lumos!

Lumos is a personal-project chat companion built by [@marcohost33-maker](https://github.com/marcohost33-maker) as part of the Coworkerz collective. It's the only **public** repo in the collective — the rest are private research/product code.

## What Lumos is

A single-file React app + Anthropic-API client, with:
- Pixel-engine Canvas2D companion
- Streaming (SSE), prompt-editor, max-tokens / temperature sliders, retry-backoff
- localStorage persistence + export/import

## Scope of contributions

Because Lumos is part of a larger personal stack (ADR LUMOS-001 deliberately keeps it single-file + Anthropic-API + zero shared deps with other coworkerz repos), the scope for external contributions is narrow:

### Welcome

- **Bug reports** — UX glitches, accessibility issues, API edge cases
- **Security findings** — see `SECURITY.md` for the reporting channel
- **Documentation** — README clarifications, broken links, typos
- **Small UX fixes** — keyboard navigation, contrast, focus management
- **Browser-compatibility patches** — older Safari, mobile-specific quirks

### Not in scope (please open an issue first)

- Multi-file refactors (single-file constraint is intentional)
- Switching to another LLM provider (Anthropic-only is a design choice)
- Adding telemetry, analytics, or external services
- Server-side / backend components
- Build-tool changes (Vite + vite-plugin-singlefile is the canon)

If you have an idea that doesn't fit "welcome" above, **open an issue first** before coding — it might already be incompatible with ADR LUMOS-001.

## How to submit a change

1. **Open an issue first** describing the problem and your proposed fix (skip for trivial typos).
2. **Fork + branch** off `main` with a descriptive name (`fix/contrast-dark-mode`, `docs/typo-readme`, etc).
3. **Keep the diff minimal** — one logical change per PR.
4. **Run locally:**
   - `npm install` (only on first checkout)
   - `npm run build` (must succeed without warnings)
   - Open `dist/index.html` in Chrome + Firefox + Safari and verify your change
5. **No dependencies added** unless absolutely required (single-file constraint).
6. **Submit PR** with:
   - What changed and why (1-2 sentences)
   - Browser-test evidence (which browsers, what you checked)
   - Reference the issue number

## Code style

- React functional components, hooks
- 2-space indent, single quotes, no semicolons-when-redundant
- Comments only for non-obvious *why*, not *what*
- Don't reorganize unrelated code in your PR

## Review timeline

- Bug reports: acknowledged within ~3 business days
- PRs: reviewed within ~7 business days

This is a personal project — patience appreciated.

## License

Lumos is currently **license-pending** (see ADR-019 in the parent Coworkerz collective). Contributing means you agree your changes can be re-licensed under the final license chosen by the maintainer.

## Code of Conduct

Lumos follows the [Contributor Covenant 2.1](./CODE_OF_CONDUCT.md). Be kind, assume good intent, no harassment.

## Questions?

Open an issue with the `question` label, or email <marcohost33@gmail.com>.

---

*Lumos is a positive AI companion. Let's keep this community positive too.*