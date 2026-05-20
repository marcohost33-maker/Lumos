# Lumos Web v1.7.1 — Single-File React Standalone

Diese Variante ist eine **Web-Reinkarnation** von Lumos — ein Chat-/KI-Begleiter
als Single-File React-App, der Anthropic API direkt aus dem Browser anspricht
(BYO API-Key in localStorage).

Sie ist **nicht** ein Replacement für das Python-Lumos im Hauptverzeichnis
(`src/`, `pyproject.toml`) — beide existieren parallel mit unterschiedlichem
Distribution-Modell.

## Files

- `lumos_v1.7.1_2026-05-20.jsx` (~95 KB) — Single-File React-Source (audit-driven):
  - Aktuelle Model-IDs May 2026 (Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
  - SSE-Streaming via fetch + ReadableStream + TextDecoder
  - System-Prompt-Editor, max_tokens-Slider, Temperature-Slider
  - Token-Usage-Display, Prompt-Caching (ephemeral)
  - Retry-Backoff (429/503/529, exp), Stop-Button, Input-Cap
  - ErrorBoundary, Page-Visibility (zukünftig)
  - **v1.7.1 Patches:** API-Key sanitize (ASCII-only, verhindert
    "non ISO-8859-1 code point" fetch-Exception bei NBSP/Curly-Quote-Paste),
    Backspace Long-Press + Doppeltap-Wort, Tab-Title-Fix
- `Lumos-v1.7.1-standalone.html` (~230 KB) — gebautes Single-File-Bundle
- `lumos_v1.7_2026-05-20.jsx` — v1.7 Source (Vorgaenger, ohne Sanitize)

## Lineage

- v1.4 (2026-05-19): Architecture-Notes
- v1.5 (2026-05-19): localStorage Persistenz
- v1.6 (2026-05-19): API-Key Settings-Panel
- v1.7 (2026-05-20): Streaming + System-Prompt-Editor + Hardening
- v1.7.1 (2026-05-20): User-Report-Fixes (ASCII-Sanitize, Backspace-UX)

Patterns extrahiert in `Vero/Recherche/Allgemein/2026-05-20_react-worker-performance-patterns.md`.

## Sicherheit

API-Key wird sanitized + lokal in `localStorage` gespeichert. CORS via
`anthropic-dangerous-direct-browser-access: true` ist legitim für BYO-API-Key-
Apps (Anthropic-anerkanntes Pattern).
