# Lumos Web v1.7.1 — Single-File React Standalone

Diese Variante ist eine **Web-Reinkarnation** von Lumos — ein Chat-/KI-Begleiter
als Single-File React-App, der Anthropic API direkt aus dem Browser anspricht
(BYO API-Key, nur für die Sitzung in sessionStorage).

Sie ist **nicht** ein Replacement für das Python-Lumos im Hauptverzeichnis
(`src/`, `pyproject.toml`) — beide existieren parallel mit unterschiedlichem
Distribution-Modell.

## Files

- `lumos_v1.7.1_2026-10-22.jsx` (~95 KB) — Single-File React-Source (audit-driven):
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
- v1.7.1 + CSP (2026-10-16): Content-Security-Policy im `<head>` des Standalone-Bundles
  (nur dort; die JSX-Quelle enthält keinen HTML-Kopf). Kein Funktionswechsel.
- v1.7.1 + Sitzungsschlüssel (2026-10-21): API-Key nur noch in `sessionStorage`; ein alter Wert aus
  `localStorage` wird beim ersten Laden einmalig übernommen und dort gelöscht (bei jedem Laden,
  auch wenn die Sitzung schon einen Schlüssel hat). Die Vorgänger-Quelle v1.7 trägt dieselbe
  Speicherregel. Das Bundle wurde
  gezielt an den zwei Speicherfunktionen und am Hinweistext gepatcht (im Repo gibt es keine
  Build-Kette); die JSX-Quelle trägt dieselbe Änderung, der CSP-Hash ist neu gesetzt.
- v1.7.1 + Speicherfehler (2026-10-22): Quelle umbenannt von `lumos_v1.7.1_2026-05-20.jsx` auf
  `lumos_v1.7.1_2026-10-22.jsx` (der Mai-Stand liegt in der Git-Historie, nicht mehr im Baum,
  weil er den Schlüssel noch in `localStorage` schrieb). Lehnt die Sitzung die Übernahme ab
  (Quota, `SecurityError`), bedient der Schlüssel die Seite aus dem Speicher; wirft das Lesen
  von `localStorage`, bleibt ein Sitzungsschlüssel erhalten; ein leerer Sitzungswert übernimmt
  den alten Schlüssel. Gleiche Regel in v1.7 und im Bundle (gezielt gepatcht, CSP-Hash neu).

Patterns extrahiert in `Vero/Recherche/Allgemein/2026-05-20_react-worker-performance-patterns.md`.

## Sicherheit

API-Key wird sanitized und nur für die Sitzung in `sessionStorage` gehalten (endet mit dem Tab;
nach dem Schliessen muss er neu eingegeben werden). Gemessen 2026-10-21 in Chromium unter `file://`:
Ein alter Schlüssel aus `localStorage` landet nach dem Laden in `sessionStorage`, `localStorage` ist
danach leer, ein Reload behält ihn, und eine andere lokale HTML-Datei in einem neuen Tab liest
nichts mehr (der alte Stand: sie las den Schlüssel). `tests/test_web_key_storage.py` prüft JSX und
Bundle darauf, dass der Schlüssel nie mehr nach `localStorage` geschrieben wird;
`tests/test_web_key_storage_dynamic.py` führt die Speicherfunktionen aller drei Dateien in Node
gegen Fake-Speicher aus (nur alt, nur Sitzung, beide, leerer Sitzungswert, Lese-/Schreibfehler,
keine `sessionStorage`, Speichern und Neuladen). `tests/test_web_key_storage_browser.py` lädt das
ausgelieferte Bundle in Chromium unter `file://` (Netz gesperrt) und beobachtet den Schlüssel dreifach:
Spion auf `Storage.prototype`, ein zweiter Tab derselben `file://`-Origin, der jedes `storage`-Ereignis
von `localStorage` sieht (auch Index-Schreibweisen ohne `setItem`), und ein Scan des Endzustands.
Fälle: nur alt, nur Sitzung, beide, leerer Sitzungswert, `localStorage` bzw. `sessionStorage`
verweigert (`SecurityError`), Eingabe im Einstellungsdialog und Neuladen, Leer-Speichern, neuer Tab
und `noopener`-Popup (lesen nichts), dazu CSP-Verstösse und Seitenfehler (keine). Gemessen
2026-10-22 (Chromium 141, Playwright 1.56): 10/10 grün; das Bundle von `main` (vor der Umstellung)
9/10 rot. Vier Mutanten, die den Schlüssel zusätzlich nach `localStorage` schreiben (berechneter
Name, Alias `window['local'+'Storage']`, `Storage.prototype.setItem.call`, Index-Schreibweise),
werden alle rot; die statische Prüfung erkennt nur die Index-Schreibweise. Der CI-Job `web-browser`
führt den Test aus und darf ihn nicht überspringen. CORS via
`anthropic-dangerous-direct-browser-access: true` ist legitim für BYO-API-Key-
Apps (Anthropic-anerkanntes Pattern).

### Content-Security-Policy (seit 2026-10-16)

Das Standalone-Bundle trägt eine CSP als `<meta>`-Tag:
`default-src 'none'`, Skripte nur per SHA-256-Hash des einen Inline-Bundles,
`connect-src https://api.anthropic.com`, `base-uri`/`form-action`/`object-src 'none'`.
Gemessen in Chrome: Die App rendert ohne Verstoss. Blockiert und als Verstoss gemeldet werden
ein `fetch` zu einer fremden Domain, ein Bild-Beacon und ein nachträglich eingefügtes
Inline-Skript (ohne CSP läuft dieses Skript). Ein eingeschleustes Skript kann den Schlüssel also
weder ausführen lassen noch über `fetch`, Bilder oder Formulare an einen fremden Server senden.
`tests/test_web_csp.py` prüft, dass die Policy vorhanden ist und ihr Hash zu den Skript-Bytes passt.
**Nach jedem Rebuild muss der Hash neu gesetzt werden**, sonst blockiert die Seite ihr eigenes
Skript (der Test schlägt dann fehl).

### Restrisiken (ehrlich)

- **`file://` teilt den Speicher:** In Chrome teilen sich alle `file://`-Seiten denselben
  `localStorage` (gemessen 2026-10-16). Deshalb liegt der Schlüssel seit 2026-10-21 nur noch in
  `sessionStorage`, das an den Tab gebunden ist. Rest: Navigiert derselbe Tab zu einer anderen
  lokalen HTML-Datei, kann diese die Sitzung desselben Tabs lesen (gemessen 2026-10-22). Modell-, Prompt- und
  Temperatur-Einstellungen bleiben bewusst in `localStorage` (keine Geheimnisse).
- `sessionStorage` ist kein Geheimnisspeicher: Ein Fenster, das aus diesem Tab mit Opener
  geöffnet wird, erhält eine Kopie der Sitzung (Spezifikation, MDN; gemessen 2026-10-22, mit
  `noopener` keine Kopie). Die App selbst öffnet keine Fenster (einziger Link: der Download-Anker
  des Exports). Beide Restrisiken hält `test_residual_risks_documented_in_the_readme_still_hold`
  fest; ändert ein Browser das Verhalten, wird dieser Text angepasst, nicht der Test. Wirft der Browser beim
  Zugriff unter `file://` einen `SecurityError`, lebt der Schlüssel nur im Speicher der Seite und
  ist nach dem Neuladen weg. Eine Variante nur im Speicher oder eine eigene, isolierte Origin
  wäre die nächste Stufe (Cross-Family-Hinweis LUM-18-02, 2026-10-21).
- Eine Option "Schlüssel dauerhaft merken" gibt es nicht; sie bräuchte UI-Code im Bundle und
  würde das obige Risiko für diesen Nutzer zurückbringen.
- Browser-Erweiterungen mit Seitenzugriff können `localStorage` lesen; das verhindert keine CSP.
- Eine Meta-CSP verhindert keine Exfiltration per Navigation (`location = ...`).
- Den Schlüssel am besten als eigenen, eng begrenzten Key mit Ausgabenlimit anlegen.
