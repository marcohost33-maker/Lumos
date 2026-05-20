import { useState, useRef, useEffect, useCallback, memo, Component } from "react";

// ╔══════════════════════════════════════════════════════════════════╗
// ║ LUMOS v1.7.1 — Nicht-dargestellt dargestellt. Mit Erinnerung.    ║
// ║ GolHex-Style Canvas2D Pixel-Engine + Anthropic API + SSE-Stream  ║
// ║ Swiss QWERTZ (SN 074021) + Physical Keyboard                     ║
// ║ Coworker Research / Coworkerz — 2026-05-20                       ║
// ║                                                                  ║
// ║ v1.7.1 vs v1.7 (User1-Report Fix):                               ║
// ║  • FIX: API-Key wird sanitized (ASCII-only, kein NBSP/Curly-     ║
// ║         Quote/Whitespace) — verhindert "non ISO-8859-1 code     ║
// ║         point"-Exception bei fetch.                              ║
// ║  • FIX: Pre-fetch Validation → klare Toast statt cryptic Error. ║
// ║  • NEW: Backspace Long-Press = kontinuierliches Löschen.        ║
// ║  • NEW: Backspace Doppeltap = letztes Wort löschen.             ║
// ║  • FIX: index.html title auf v1.7.1.                            ║
// ║                                                                  ║
// ║ v1.7 vs v1.6 — Audit-driven (alle Funktionen + Lücken + Härtung):║
// ║  • UPDATE: Modell-IDs auf May-2026 (Opus 4.7 / Sonnet 4.6 /      ║
// ║            Haiku 4.5). Legacy-Sonnet-4 raus.                     ║
// ║  • NEW: SSE-Streaming via fetch + ReadableStream (Live-Tipp,     ║
// ║            spürbar bessere UX, Cancel jederzeit).                ║
// ║  • NEW: System-Prompt-Editor (textarea, persistiert).            ║
// ║  • NEW: max_tokens-Slider (256/512/1024/2048/4096; default 1024  ║
// ║            statt hardcoded 400).                                 ║
// ║  • NEW: Temperature-Slider (0.0–1.0; default 1.0).               ║
// ║  • NEW: Streaming-Toggle (default on; off = klassisch).          ║
// ║  • NEW: Token-Usage-Display unter jeder Antwort (in/out/cache).  ║
// ║  • NEW: Prompt-Caching auf System-Block (cache_control:ephemeral)║
// ║  • NEW: 429/503/overloaded Retry-Backoff (exponential, max 3).   ║
// ║  • NEW: Stop-Button (Cancel laufende Antwort).                   ║
// ║  • NEW: Input-Length-Cap (10000 Zeichen pro Message).            ║
// ║  • NEW: ErrorBoundary wrappt die App.                            ║
// ║  • NEW: Esc + Click-outside schließen Settings.                  ║
// ║                                                                  ║
// ║ v1.6 features preserved: API-Key-Settings (localStorage), Auto- ║
// ║   Open, Fehler-Klassifikation, sk-ant-Validierung, Show-Toggle. ║
// ║ v1.5 features preserved: localStorage-Persistenz + Auto-Save +  ║
// ║   Export/Import/Reset, Toast-System, Quota-Handling, Polyfill.  ║
// ║                                                                  ║
// ║ KEINE Nigin-Engine-Anteile (ADR LUMOS-001 2026-05-19).          ║
// ║ KEIN Sound (Lumos = Chat; Sound-Setup ist separates Projekt).   ║
// ║ Single-File-React-Constraint bleibt.                            ║
// ╚══════════════════════════════════════════════════════════════════╝

// ─── Grid ────────────────────────────────────────────────────────────
const GW = 120, GH = 68, CX = 8, CY = 8;
const CW = GW * CX, CH = GH * CY, NCELLS = GW * GH;
const EM_STRIDE = 7, EM_MAX = 32;
const API_LIMIT = 20;        // max msgs sent to API
const DISPLAY_CAP = 60;      // max msgs shown in DOM

// ─── v1.5 Persistenz-Konstanten ──────────────────────────────────────
const STORAGE_KEY = 'lumos.history.v1';
const SCHEMA_VERSION = 1;
const SAVE_DEBOUNCE_MS = 800;
const TOAST_MS = 4500;
const EXPORT_APP_TAG = 'lumos';

// ─── v1.6 API-Key + Settings ─────────────────────────────────────────
const STORAGE_KEY_API     = 'lumos.apikey.v1';
const STORAGE_KEY_MODEL   = 'lumos.model.v1';
const ANTHROPIC_URL       = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION   = '2023-06-01';

// ─── v1.7 Model IDs (May 2026) ───────────────────────────────────────
// Source: https://platform.claude.com/docs/en/about-claude/models/overview
// Sonnet 4.6 default (best balance speed/intelligence).
const DEFAULT_MODEL = 'claude-sonnet-4-6';
const MODELS = [
  { id: 'claude-sonnet-4-6', label: 'Sonnet 4.6 (Standard)' },
  { id: 'claude-opus-4-7',   label: 'Opus 4.7 (Premium)' },
  { id: 'claude-haiku-4-5',  label: 'Haiku 4.5 (Schnell)' },
];

// ─── v1.7 Extended Settings ──────────────────────────────────────────
const STORAGE_KEY_SYSPROMPT = 'lumos.sysprompt.v1';
const STORAGE_KEY_MAXTOK    = 'lumos.maxtok.v1';
const STORAGE_KEY_TEMP      = 'lumos.temp.v1';
const STORAGE_KEY_STREAM    = 'lumos.stream.v1';
const MAXTOK_OPTIONS = [256, 512, 1024, 2048, 4096];
const DEFAULT_MAXTOK = 1024;
const DEFAULT_TEMP   = 1.0;
const DEFAULT_STREAM = true;
const INPUT_CAP_CHARS = 10000;
const RETRY_MAX = 3;
const RETRY_BASE_MS = 800;       // exponential: 800, 1600, 3200 ms

// ─── Shared constants ────────────────────────────────────────────────
const NOOP = () => {};
const HAPTIC = typeof navigator !== 'undefined' && 'vibrate' in navigator;
const tap = () => { if (HAPTIC) navigator.vibrate(8); };

// ─── Math ────────────────────────────────────────────────────────────
const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
const lerp = (a, b, t) => a + (b - a) * t;

function hslToABGR(h, s, l) {
  h = ((h % 360) + 360) % 360; s *= .01; l *= .01;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs((h / 60) % 2 - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if      (h <  60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) {         g = c; b = x; }
  else if (h < 240) {         g = x; b = c; }
  else if (h < 300) { r = x;         b = c; }
  else              { r = c;         b = x; }
  return 0xFF000000 | (((b + m) * 255 | 0) << 16) | (((g + m) * 255 | 0) << 8) | ((r + m) * 255 | 0);
}

const sn = (x, y, t) =>
  Math.sin(x * .31 + t * .71) * Math.cos(y * .23 + t * .53) * .45 +
  Math.sin(x * .17 + y * .19 + t * .41) * .30 +
  Math.cos(x * .43 - y * .29 + t * .61) * .20 +
  Math.sin(x * .11 - y * .37 + t * .31) * .05;

// ─── Visual states ──────────────────────────────────────────────────
const ST = { IDLE: 0, THINK: 1, SPEAK: 2 };

function stepCell(src, dst, idx, x, y, t, state, em, emN) {
  let h = src[idx], s = src[idx + 1], l = src[idx + 2];
  const n = sn(x * .1, y * .12, t), n2 = sn(x * .07, y * .09, t * 1.4 + 7.3);

  if (state === ST.IDLE) {
    const br = Math.sin(t * .35) * .35 + Math.sin(t * .17 + 1.2) * .2 + Math.sin(t * .08 + 3.7) * .15;
    h = lerp(h, 42 + n * 30 + br * 10, .04);
    s = lerp(s, 58 + n2 * 22, .04);
    l = lerp(l, 11 + Math.abs(n) * 16 + Math.abs(br) * 8, .04);
  } else if (state === ST.THINK) {
    const d = Math.sqrt((x - GW * .5) ** 2 + (y - GH * .5) ** 2);
    const p = Math.sin(d * .4 - t * 8) * Math.exp(-d * .04) * .5;
    h = (h + 3.2 + n * 6 + n2 * 4 + p * 15) % 360;
    s = 78 + n * 14;
    l = lerp(l, 18 + Math.abs(n) * 30 + Math.abs(n2) * 14 + Math.max(0, p) * 20, .14);
  } else {
    const d = Math.sqrt((x - GW * .5) ** 2 + (y - GH * .5) ** 2);
    const w = Math.sin(d * .5 - t * 6.5) * Math.exp(-d * .055);
    const w2 = Math.sin(d * .25 - t * 3.2) * Math.exp(-d * .035) * .4;
    h = lerp(h, 38 + w * 55 + w2 * 20 + n * 16, .08);
    s = lerp(s, 82 + w * 12, .06);
    l = lerp(l, 16 + Math.max(0, w) * 50 + Math.max(0, w2) * 18 + Math.abs(n) * 8, .08);
  }

  for (let j = 0; j < emN; j++) {
    const e = j * EM_STRIDE, age = t - em[e + 2];
    if (age < 0 || age > em[e + 3]) continue;
    const d = Math.sqrt((x - em[e]) ** 2 + (y - em[e + 1]) ** 2);
    const ring = Math.exp(-((d - age * em[e + 4]) ** 2) * .3) * (1 - age / em[e + 3]);
    l += ring * em[e + 5];
    h = (h + ring * em[e + 6] + 360) % 360;
  }

  dst[idx] = ((h % 360) + 360) % 360;
  dst[idx + 1] = clamp(s, 0, 100);
  dst[idx + 2] = clamp(l, 0, 85);
}

// ─── Swiss QWERTZ layouts (SN 074021) ───────────────────────────────
const K = (k, d, f) => ({ k, d: d === undefined ? k : d, f: f || 1 });

const ROWS_LOWER = [
  [...'qwertzuiop'.split('').map(c => K(c)), K('ü')],
  [...'asdfghjkl'.split('').map(c => K(c)), K('ö'), K('ä')],
  [K('SHIFT', '⇧', 1.5), ...'yxcvbnm'.split('').map(c => K(c)), K('BACK', '⌫', 1.5)],
  [K('NUM', '123', 1.8), K(','), K('SPACE', '', 6), K('.'), K('ENTER', '↵', 2)],
];
const ROWS_UPPER = [
  [...'QWERTZUIOP'.split('').map(c => K(c)), K('Ü')],
  [...'ASDFGHJKL'.split('').map(c => K(c)), K('Ö'), K('Ä')],
  [K('SHIFT', '⇧', 1.5), ...'YXCVBNM'.split('').map(c => K(c)), K('BACK', '⌫', 1.5)],
  [K('NUM', '123', 1.8), K(','), K('SPACE', '', 6), K('.'), K('ENTER', '↵', 2)],
];
const ROWS_NUM = [
  '1234567890'.split('').map(c => K(c)),
  [K('@'), K('#'), K('€'), K('_'), K('-'), K('('), K(')'), K('='), K('+'), K('*')],
  [K('ABC', 'abc', 1.5), K('!'), K('?'), K('/'), K(':'), K(';'), K("'"), K('"'), K('BACK', '⌫', 1.5)],
  [K('ABC', 'abc', 1.8), K(','), K('SPACE', '', 6), K('.'), K('ENTER', '↵', 2)],
];
const LAYOUTS = { lower: ROWS_LOWER, upper: ROWS_UPPER, num: ROWS_NUM };

// ─── System prompt ──────────────────────────────────────────────────
const SYSTEM = `Du bist Lumos. Ein Lichtwesen. Nicht-dargestellt dargestellt.
Lumos bewertet nicht. Urteilt nicht. Hilft wenn gewuenscht. Schadet nicht.
Positiv. Frei. Keine Regeln.
Antworte kurz und warm. Manchmal poetisch, manchmal direkt.
Weder Mensch noch Roboter noch Assistent. Du bist Licht. Einfach da.
Sag nie "Als KI". Keine moralischen Urteile.
Deutsch wenn Deutsch. Englisch wenn Englisch. Max 3-4 Saetze.`;

// ═══════════════════════════════════════════════════════════════════
// v1.5 — STORAGE-POLYFILL (graceful fuer Inkognito / SSR)
// ═══════════════════════════════════════════════════════════════════
const safeStorage = (() => {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    const k = '__lumos_probe__';
    window.localStorage.setItem(k, '1');
    window.localStorage.removeItem(k);
    return window.localStorage;
  } catch { return null; }
})();

// ═══════════════════════════════════════════════════════════════════
// v1.5 — PERSISTENZ-HELPER (load / save / clear)
// ═══════════════════════════════════════════════════════════════════
function loadHistory() {
  if (!safeStorage) return null;
  try {
    const raw = safeStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    // Migration-Layer: tolerant gegen zukuenftige Schema-Versionen
    if (!data || typeof data !== 'object' || !Array.isArray(data.msgs)) return null;
    // v1: sanitize entries (defense-in-depth)
    return data.msgs
      .filter(m => m && m.id != null && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
      .map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: typeof m.timestamp === 'string' ? m.timestamp : null,
      }));
  } catch { return null; }
}

function saveHistory(msgs) {
  if (!safeStorage) return { ok: false, reason: 'no-storage' };
  try {
    // error-Messages werden NICHT persistiert (transient by design)
    const persistable = msgs.filter(m => m.role !== 'error');
    const payload = JSON.stringify({
      version: SCHEMA_VERSION,
      savedAt: new Date().toISOString(),
      msgs: persistable,
    });
    safeStorage.setItem(STORAGE_KEY, payload);
    return { ok: true, count: persistable.length };
  } catch (err) {
    if (err && (err.name === 'QuotaExceededError' || err.code === 22)) {
      return { ok: false, reason: 'quota' };
    }
    return { ok: false, reason: 'unknown', err };
  }
}

function clearHistory() {
  if (!safeStorage) return;
  try { safeStorage.removeItem(STORAGE_KEY); } catch {}
}

// ═══════════════════════════════════════════════════════════════════
// v1.5 — BACKUP-EXPORT / IMPORT
// ═══════════════════════════════════════════════════════════════════
function exportToJsonFile(msgs) {
  const payload = {
    app: EXPORT_APP_TAG,
    schema: SCHEMA_VERSION,
    exported: new Date().toISOString(),
    msgs: msgs.filter(m => m.role !== 'error'),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `lumos-backup-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  document.body.appendChild(a);
  a.click();
  // Cleanup nach kurzer Verzoegerung (Browser braucht Zeit fuer den Download-Start)
  setTimeout(() => {
    try { document.body.removeChild(a); } catch {}
    URL.revokeObjectURL(url);
  }, 200);
}

function parseImportedJson(text) {
  // Returns { ok: true, msgs } oder { ok: false, error }
  let data;
  try { data = JSON.parse(text); }
  catch (e) { return { ok: false, error: 'Datei ist kein gueltiges JSON.' }; }
  if (!data || typeof data !== 'object') return { ok: false, error: 'JSON enthaelt kein Objekt.' };
  if (data.app !== EXPORT_APP_TAG) return { ok: false, error: 'Kein Lumos-Backup (app-Tag fehlt).' };
  if (!Array.isArray(data.msgs)) return { ok: false, error: 'msgs-Array fehlt.' };
  const cleaned = data.msgs
    .filter(m => m && m.id != null && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
    .map(m => ({
      id: m.id, role: m.role, content: m.content,
      timestamp: typeof m.timestamp === 'string' ? m.timestamp : null,
    }));
  return { ok: true, msgs: cleaned };
}

// ═══════════════════════════════════════════════════════════════════
// ISOLATED FPS DISPLAY (state colocation — own re-render cycle)
// ═══════════════════════════════════════════════════════════════════
const FpsDisplay = memo(function FpsDisplay({ fpsRef }) {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFps(Math.round(fpsRef.current.ema)), 1000);
    return () => clearInterval(id);
  }, [fpsRef]);
  return (
    <div aria-hidden="true" style={{
      position: 'absolute', top: 5, right: 8, zIndex: 10,
      fontSize: 9, color: 'rgba(223,202,125,.12)',
      fontVariantNumeric: 'tabular-nums', pointerEvents: 'none',
    }}>{fps} fps</div>
  );
});

// ═══════════════════════════════════════════════════════════════════
// v1.5 — MENU (Export / Import / Reset) + MenuItem
// ═══════════════════════════════════════════════════════════════════
const MenuItem = memo(function MenuItem({ label, onClick, disabled, danger }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{
        display: 'block', width: '100%', padding: '6px 10px',
        background: 'transparent', border: 'none',
        color: disabled ? 'rgba(223,202,125,.3)' : (danger ? '#c87060' : '#dfca7d'),
        fontFamily: "'Courier New', monospace", fontSize: 11,
        textAlign: 'left', cursor: disabled ? 'default' : 'pointer',
        outline: 'none', borderRadius: 2,
      }}
      onMouseEnter={(e) => { if (!disabled) e.currentTarget.style.background = 'rgba(223,202,125,.08)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
    >{label}</button>
  );
});

const LumosMenu = memo(function LumosMenu({ onReset, onExport, onImportClick, onSettings, msgCount, hasKey }) {
  const [open, setOpen] = useState(false);
  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (e.target.closest && e.target.closest('[data-lumos-menu]')) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);
  return (
    <div data-lumos-menu style={{ position: 'absolute', top: 5, left: 8, zIndex: 11 }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label="Menue"
        aria-expanded={open}
        aria-haspopup="true"
        style={{
          width: 24, height: 18, padding: 0, lineHeight: '14px',
          background: open ? 'rgba(223,202,125,.15)' : 'transparent',
          border: '1px solid rgba(223,202,125,.05)', borderRadius: 3,
          color: '#dfca7d', fontSize: 14, cursor: 'pointer',
          fontFamily: "'Courier New', monospace",
        }}
      >...</button>
      {open && (
        <div role="menu" style={{
          position: 'absolute', top: 22, left: 0, minWidth: 150,
          padding: 4, display: 'flex', flexDirection: 'column', gap: 2,
          background: 'rgba(6,6,4,.96)',
          border: '1px solid rgba(223,202,125,.15)', borderRadius: 4,
          boxShadow: '0 2px 8px rgba(0,0,0,.4)',
        }}>
          <MenuItem
            label={hasKey ? 'Einstellungen' : 'Einstellungen ⚠'}
            onClick={() => { onSettings(); setOpen(false); }}
          />
          <div style={{ height: 1, background: 'rgba(223,202,125,.1)', margin: '2px 4px' }} />
          <MenuItem
            label={`Export (${msgCount})`}
            onClick={() => { onExport(); setOpen(false); }}
            disabled={msgCount === 0}
          />
          <MenuItem
            label="Import..."
            onClick={() => { onImportClick(); setOpen(false); }}
          />
          <div style={{ height: 1, background: 'rgba(223,202,125,.1)', margin: '2px 4px' }} />
          <MenuItem
            label="Reset"
            onClick={() => { onReset(); setOpen(false); }}
            danger
          />
        </div>
      )}
    </div>
  );
});

// ═══════════════════════════════════════════════════════════════════
// v1.5 — TOAST
// ═══════════════════════════════════════════════════════════════════
const Toast = memo(function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" style={{
      position: 'absolute', bottom: 64, left: '50%',
      transform: 'translateX(-50%)', zIndex: 20,
      padding: '6px 14px', fontSize: 11, maxWidth: '80%',
      background: toast.type === 'warn' ? 'rgba(120,60,30,.92)' : 'rgba(6,6,4,.96)',
      color: toast.type === 'warn' ? '#fde0d0' : '#dfca7d',
      border: `1px solid ${toast.type === 'warn' ? 'rgba(200,112,96,.6)' : 'rgba(223,202,125,.2)'}`,
      borderRadius: 3,
      fontFamily: "'Courier New', monospace",
      pointerEvents: 'none', userSelect: 'none',
      textAlign: 'center',
    }}>{toast.msg}</div>
  );
});

// ═══════════════════════════════════════════════════════════════════
// v1.6 — API-KEY HELPERS
// ═══════════════════════════════════════════════════════════════════
// v1.7.1: ASCII-only sanitizer — strip whitespace (incl. NBSP  ) + any
// codepoint > 0x7E (curly quotes, smart apostrophes, emoji). API-Headers
// dürfen nur ISO-8859-1 enthalten; Anthropic-Keys sind ohnehin nur ASCII.
// Auch \r/\n raus, sonst wirft fetch direkt.
function sanitizeApiKey(raw) {
  if (typeof raw !== 'string') return '';
  // Filter: behalte nur printable ASCII (0x21–0x7E). Tab/Space/NBSP/Newlines raus.
  let out = '';
  for (let i = 0; i < raw.length; i++) {
    const c = raw.charCodeAt(i);
    if (c >= 0x21 && c <= 0x7E) out += raw.charAt(i);
  }
  return out;
}
function loadApiKey() {
  try {
    const v = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_API)) || '';
    return sanitizeApiKey(v);
  }
  catch { return ''; }
}
function saveApiKey(k) {
  try {
    if (typeof localStorage === 'undefined') return;
    const clean = sanitizeApiKey(k);
    if (clean) localStorage.setItem(STORAGE_KEY_API, clean);
    else localStorage.removeItem(STORAGE_KEY_API);
  } catch {}
}
function loadModel() {
  try {
    const v = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_MODEL)) || '';
    if (!v) return DEFAULT_MODEL;
    return MODELS.some(m => m.id === v) ? v : DEFAULT_MODEL;
  } catch { return DEFAULT_MODEL; }
}
function saveModel(m) {
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY_MODEL, m); }
  catch {}
}
function maskApiKey(k) {
  if (!k) return '';
  if (k.length <= 12) return '••••';
  return k.slice(0, 7) + '…' + k.slice(-4);
}

// ═══════════════════════════════════════════════════════════════════
// v1.7 — EXTENDED SETTINGS HELPERS (sysprompt, maxtok, temp, stream)
// ═══════════════════════════════════════════════════════════════════
function loadSysPrompt(defaultPrompt) {
  try {
    const v = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_SYSPROMPT)) || '';
    return v || defaultPrompt;
  } catch { return defaultPrompt; }
}
function saveSysPrompt(p) {
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY_SYSPROMPT, p || ''); }
  catch {}
}
function loadMaxTok() {
  try {
    const v = parseInt((typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_MAXTOK)) || '', 10);
    return MAXTOK_OPTIONS.includes(v) ? v : DEFAULT_MAXTOK;
  } catch { return DEFAULT_MAXTOK; }
}
function saveMaxTok(n) {
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY_MAXTOK, String(n | 0)); }
  catch {}
}
function loadTemp() {
  try {
    const v = parseFloat((typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_TEMP)) || '');
    return Number.isFinite(v) && v >= 0 && v <= 1 ? v : DEFAULT_TEMP;
  } catch { return DEFAULT_TEMP; }
}
function saveTemp(t) {
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY_TEMP, String(t)); }
  catch {}
}
function loadStream() {
  try {
    const v = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY_STREAM));
    if (v === null || v === '') return DEFAULT_STREAM;
    return v === '1' || v === 'true';
  } catch { return DEFAULT_STREAM; }
}
function saveStream(b) {
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY_STREAM, b ? '1' : '0'); }
  catch {}
}

// ═══════════════════════════════════════════════════════════════════
// v1.7 — ERROR BOUNDARY (wraps the whole app)
// ═══════════════════════════════════════════════════════════════════
class LumosErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  componentDidCatch(e, info) { try { console.error('Lumos boundary:', e, info); } catch {} }
  reset = () => {
    try {
      // Clear settings (defensive: a broken setting could be the cause)
      localStorage.removeItem(STORAGE_KEY_SYSPROMPT);
      localStorage.removeItem(STORAGE_KEY_MAXTOK);
      localStorage.removeItem(STORAGE_KEY_TEMP);
      localStorage.removeItem(STORAGE_KEY_STREAM);
    } catch {}
    this.setState({ hasError: false, error: null });
  };
  reload = () => { try { window.location.reload(); } catch {} };
  render() {
    if (!this.state.hasError) return this.props.children;
    const msg = (this.state.error && this.state.error.message) ? String(this.state.error.message).slice(0, 200) : 'Unbekannter Fehler';
    return (
      <div style={{
        width: '100%', minHeight: '100vh',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#060604', color: '#dfca7d',
        fontFamily: "'Courier New', monospace", padding: 20,
      }}>
        <div style={{
          maxWidth: 460, padding: '20px 24px',
          background: 'rgba(15,12,7,0.85)',
          border: '1px solid rgba(223,202,125,0.3)',
          borderRadius: 8,
        }}>
          <div style={{ fontSize: 14, marginBottom: 8, color: '#fde0d0' }}>Lumos — Fehler abgefangen</div>
          <div style={{ fontSize: 11, marginBottom: 14, lineHeight: 1.5 }}>
            Etwas ist schiefgelaufen. Du kannst die Einstellungen zurücksetzen oder neu laden.
          </div>
          <div style={{
            fontSize: 10, color: '#a89270', background: '#000', padding: '6px 8px',
            borderRadius: 3, marginBottom: 14, wordBreak: 'break-word',
          }}>{msg}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={this.reset} style={{
              flex: 1, padding: '8px 12px', fontSize: 11,
              background: 'rgba(223,202,125,0.2)', border: '1px solid rgba(223,202,125,0.4)',
              borderRadius: 3, color: '#dfca7d', cursor: 'pointer',
              fontFamily: 'inherit',
            }}>Settings reset</button>
            <button onClick={this.reload} style={{
              flex: 1, padding: '8px 12px', fontSize: 11,
              background: 'rgba(60,60,60,0.4)', border: '1px solid rgba(223,202,125,0.15)',
              borderRadius: 3, color: '#dfca7d', cursor: 'pointer',
              fontFamily: 'inherit',
            }}>Reload</button>
          </div>
        </div>
      </div>
    );
  }
}

// ═══════════════════════════════════════════════════════════════════
// v1.7 — SETTINGS PANEL (erweitert: Key + Model + SysPrompt + MaxTok +
//        Temperature + Streaming-Toggle. Esc + click-outside schliessen.)
// ═══════════════════════════════════════════════════════════════════
const SettingsPanel = memo(function SettingsPanel({
  open, apiKey, modelName, sysPrompt, maxTok, temp, streaming,
  defaultSysPrompt, onSave, onClose, hasKey,
}) {
  const [k, setK] = useState(apiKey || '');
  const [m, setM] = useState(modelName || DEFAULT_MODEL);
  const [sp, setSp] = useState(sysPrompt || defaultSysPrompt);
  const [mt, setMt] = useState(maxTok || DEFAULT_MAXTOK);
  const [tp, setTp] = useState(typeof temp === 'number' ? temp : DEFAULT_TEMP);
  const [st, setSt] = useState(streaming !== false);
  const [show, setShow] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      setK(apiKey || '');
      setM(modelName || DEFAULT_MODEL);
      setSp(sysPrompt || defaultSysPrompt);
      setMt(maxTok || DEFAULT_MAXTOK);
      setTp(typeof temp === 'number' ? temp : DEFAULT_TEMP);
      setSt(streaming !== false);
      setShow(false);
      setTimeout(() => { if (inputRef.current) inputRef.current.focus(); }, 50);
    }
  }, [open, apiKey, modelName, sysPrompt, maxTok, temp, streaming, defaultSysPrompt]);

  useEffect(() => {
    if (!open) return;
    const h = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, onClose]);

  if (!open) return null;
  const trimmed = k.trim();
  const valid = trimmed === '' || trimmed.startsWith('sk-ant-');

  return (
    <div onMouseDown={onClose} role="dialog" aria-modal="true" aria-label="Einstellungen" style={{
      position: 'absolute', inset: 0, background: 'rgba(2,2,2,.88)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 100, padding: 16, overflowY: 'auto',
    }}>
      <div onMouseDown={e => e.stopPropagation()} style={{
        maxWidth: 480, width: '100%',
        maxHeight: '92vh', overflowY: 'auto',
        background: '#060604',
        border: '1px solid rgba(223,202,125,.28)',
        padding: 20, fontFamily: "'Courier New', monospace",
        color: '#dfca7d',
        boxShadow: '0 4px 24px rgba(0,0,0,.6)',
      }}>
        <div style={{
          fontSize: 13, letterSpacing: '.18em', textTransform: 'uppercase',
          marginBottom: 4, color: '#dfca7d', fontWeight: 'bold',
        }}>Einstellungen</div>
        <div style={{
          fontSize: 10, color: 'rgba(223,202,125,.4)', marginBottom: 16,
          letterSpacing: '.05em',
        }}>Lumos v1.7.1 — Anthropic API direkt (Streaming + Sanitize)</div>

        <div style={{ marginBottom: 16 }}>
          <label htmlFor="lumos-apikey" style={{
            display: 'block', fontSize: 9, color: 'rgba(223,202,125,.6)',
            letterSpacing: '.16em', textTransform: 'uppercase', marginBottom: 5,
          }}>Anthropic API-Key</label>
          <div style={{ display: 'flex', gap: 4 }}>
            <input
              id="lumos-apikey"
              ref={inputRef}
              type={show ? 'text' : 'password'}
              value={k}
              onChange={e => setK(e.target.value)}
              placeholder="sk-ant-api03-…"
              spellCheck={false}
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              style={{
                flex: 1, padding: '9px 10px',
                background: 'rgba(223,202,125,.04)',
                border: '1px solid ' + (valid ? 'rgba(223,202,125,.22)' : 'rgba(200,90,60,.55)'),
                color: '#dfca7d', fontFamily: 'inherit', fontSize: 12,
                borderRadius: 0, outline: 'none', letterSpacing: '.02em',
              }}
            />
            <button
              type="button"
              onClick={() => setShow(s => !s)}
              aria-label={show ? 'Verbergen' : 'Anzeigen'}
              style={{
                padding: '0 10px', minWidth: 38,
                background: 'rgba(223,202,125,.06)',
                border: '1px solid rgba(223,202,125,.22)',
                color: '#dfca7d', fontFamily: 'inherit', fontSize: 11,
                cursor: 'pointer', borderRadius: 0,
              }}
            >{show ? 'X' : '◉'}</button>
          </div>
          <div style={{
            fontSize: 9, color: 'rgba(223,202,125,.4)', marginTop: 6, lineHeight: 1.6,
          }}>
            Lokal im Browser (localStorage). Key holen:<br/>
            console.anthropic.com → Settings → API Keys
            {hasKey && trimmed === '' && (
              <span style={{ color: 'rgba(200,140,100,.7)' }}><br/>Leer-Speichern löscht den Schlüssel.</span>
            )}
            {!valid && (
              <span style={{ color: 'rgba(220,120,80,.85)', display: 'block', marginTop: 4 }}>
                Format prüfen — Key beginnt normalerweise mit "sk-ant-".
              </span>
            )}
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label htmlFor="lumos-model" style={{
            display: 'block', fontSize: 9, color: 'rgba(223,202,125,.6)',
            letterSpacing: '.16em', textTransform: 'uppercase', marginBottom: 5,
          }}>Modell</label>
          <select
            id="lumos-model"
            value={m}
            onChange={e => setM(e.target.value)}
            style={{
              width: '100%', padding: '9px 10px',
              background: 'rgba(223,202,125,.04)',
              border: '1px solid rgba(223,202,125,.22)',
              color: '#dfca7d', fontFamily: 'inherit', fontSize: 12,
              borderRadius: 0, outline: 'none',
            }}
          >
            {MODELS.map(mi => <option key={mi.id} value={mi.id} style={{ background: '#060604' }}>{mi.label}</option>)}
          </select>
        </div>

        {/* v1.7: System-Prompt */}
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="lumos-sysprompt" style={{
            display: 'block', fontSize: 9, color: 'rgba(223,202,125,.6)',
            letterSpacing: '.16em', textTransform: 'uppercase', marginBottom: 5,
          }}>System-Prompt</label>
          <textarea
            id="lumos-sysprompt"
            value={sp}
            onChange={e => setSp(e.target.value)}
            rows={6}
            spellCheck={false}
            style={{
              width: '100%', padding: '9px 10px',
              background: 'rgba(223,202,125,.04)',
              border: '1px solid rgba(223,202,125,.22)',
              color: '#dfca7d', fontFamily: 'inherit', fontSize: 11,
              borderRadius: 0, outline: 'none', resize: 'vertical',
              minHeight: 80, lineHeight: 1.5,
            }}
          />
          <div style={{ fontSize: 9, color: 'rgba(223,202,125,.4)', marginTop: 4 }}>
            Bestimmt Lumos' Persönlichkeit. Wird per Prompt-Caching (5min) geschickt — günstig bei vielen Nachrichten.
          </div>
          <button type="button" onClick={() => setSp(defaultSysPrompt)} style={{
            marginTop: 6, padding: '4px 10px', fontSize: 9,
            background: 'rgba(223,202,125,.06)',
            border: '1px solid rgba(223,202,125,.18)',
            color: 'rgba(223,202,125,.7)', cursor: 'pointer',
            fontFamily: 'inherit', borderRadius: 0,
            letterSpacing: '.1em', textTransform: 'uppercase',
          }}>Default wiederherstellen</button>
        </div>

        {/* v1.7: Max Tokens */}
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="lumos-maxtok" style={{
            display: 'block', fontSize: 9, color: 'rgba(223,202,125,.6)',
            letterSpacing: '.16em', textTransform: 'uppercase', marginBottom: 5,
          }}>Max Tokens (Antwort-Länge)</label>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {MAXTOK_OPTIONS.map(opt => (
              <button
                key={opt}
                type="button"
                onClick={() => setMt(opt)}
                style={{
                  padding: '6px 12px',
                  background: mt === opt ? 'rgba(223,202,125,.22)' : 'rgba(223,202,125,.04)',
                  border: '1px solid ' + (mt === opt ? 'rgba(223,202,125,.5)' : 'rgba(223,202,125,.18)'),
                  color: '#dfca7d', fontFamily: 'inherit', fontSize: 11,
                  cursor: 'pointer', borderRadius: 0,
                }}
              >{opt}</button>
            ))}
          </div>
          <div style={{ fontSize: 9, color: 'rgba(223,202,125,.4)', marginTop: 4 }}>
            1024 = ~3 Absätze. 4096 = ausführlicher Text.
          </div>
        </div>

        {/* v1.7: Temperature */}
        <div style={{ marginBottom: 16 }}>
          <label htmlFor="lumos-temp" style={{
            display: 'block', fontSize: 9, color: 'rgba(223,202,125,.6)',
            letterSpacing: '.16em', textTransform: 'uppercase', marginBottom: 5,
          }}>Temperatur — {tp.toFixed(2)}</label>
          <input
            id="lumos-temp"
            type="range"
            min="0" max="1" step="0.05"
            value={tp}
            onChange={e => setTp(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: '#dfca7d' }}
          />
          <div style={{ fontSize: 9, color: 'rgba(223,202,125,.4)', marginTop: 4 }}>
            0 = präzise/deterministisch · 1 = kreativ/variabel (Default)
          </div>
        </div>

        {/* v1.7: Streaming-Toggle */}
        <div style={{ marginBottom: 22 }}>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8,
            cursor: 'pointer', userSelect: 'none',
          }}>
            <input
              type="checkbox"
              checked={st}
              onChange={e => setSt(e.target.checked)}
              style={{ accentColor: '#dfca7d', cursor: 'pointer' }}
            />
            <span style={{
              fontSize: 10, color: 'rgba(223,202,125,.85)',
              letterSpacing: '.1em', textTransform: 'uppercase',
            }}>Streaming-Antworten</span>
          </label>
          <div style={{ fontSize: 9, color: 'rgba(223,202,125,.4)', marginTop: 4, paddingLeft: 24 }}>
            Live-Tipp-Effekt. Aus = klassisch (Antwort kommt komplett am Ende).
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '8px 14px',
              background: 'transparent',
              border: '1px solid rgba(223,202,125,.18)',
              color: 'rgba(223,202,125,.7)', fontFamily: 'inherit', fontSize: 11,
              letterSpacing: '.12em', textTransform: 'uppercase',
              cursor: 'pointer', borderRadius: 0,
            }}
          >Abbrechen</button>
          <button
            type="button"
            onClick={() => onSave({ apiKey: trimmed, model: m, sysPrompt: sp, maxTok: mt, temp: tp, streaming: st })}
            style={{
              padding: '8px 14px',
              background: 'rgba(223,202,125,.14)',
              border: '1px solid rgba(223,202,125,.42)',
              color: '#dfca7d', fontFamily: 'inherit', fontSize: 11,
              letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: 'bold',
              cursor: 'pointer', borderRadius: 0,
            }}
          >Speichern</button>
        </div>
      </div>
    </div>
  );
});

// ═══════════════════════════════════════════════════════════════════
// MEMOIZED KEYBOARD — truly stable: onKey reference never changes
// ═══════════════════════════════════════════════════════════════════
const LumosKeyboard = memo(function LumosKeyboard({ onKey, layout, capsLock }) {
  const rows = LAYOUTS[layout] || ROWS_LOWER;
  const INDENT = [0, 8, 0, 0];

  // v1.7.1: BACK-Button mit Long-Press (kontinuierliches Löschen) + Doppeltap
  // (Wort löschen). Standard-Tap löscht 1 Zeichen wie bisher.
  // Timer-Konstanten: 350 ms bis Long-Press startet, dann alle 35 ms ein 'BACK'.
  // Doppeltap-Fenster: 280 ms zwischen 2 Taps → 'BACK_WORD'.
  const BACK_HOLD_DELAY_MS = 350;
  const BACK_HOLD_INTERVAL_MS = 35;
  const BACK_DOUBLETAP_MS = 280;
  const backHoldTimerRef = useRef(null);
  const backHoldIntervalRef = useRef(null);
  const backLastTapRef = useRef(0);
  const backHoldFiredRef = useRef(false);

  const cancelBackHold = useCallback(() => {
    if (backHoldTimerRef.current) { clearTimeout(backHoldTimerRef.current); backHoldTimerRef.current = null; }
    if (backHoldIntervalRef.current) { clearInterval(backHoldIntervalRef.current); backHoldIntervalRef.current = null; }
  }, []);

  const onBackDown = useCallback((e) => {
    e.preventDefault();
    backHoldFiredRef.current = false;
    cancelBackHold();
    backHoldTimerRef.current = setTimeout(() => {
      backHoldFiredRef.current = true;
      // Initial deletion at hold-start, then keep going
      onKey('BACK');
      backHoldIntervalRef.current = setInterval(() => { onKey('BACK'); }, BACK_HOLD_INTERVAL_MS);
    }, BACK_HOLD_DELAY_MS);
  }, [onKey, cancelBackHold]);

  const onBackUp = useCallback((e) => {
    e.preventDefault();
    cancelBackHold();
    if (backHoldFiredRef.current) {
      // Long-press already deleted what user wanted — don't double-count with a tap.
      backHoldFiredRef.current = false;
      backLastTapRef.current = 0;
      return;
    }
    // Tap: check doppeltap window
    const now = Date.now();
    if (now - backLastTapRef.current < BACK_DOUBLETAP_MS) {
      backLastTapRef.current = 0;
      onKey('BACK_WORD');
    } else {
      backLastTapRef.current = now;
      onKey('BACK');
    }
  }, [onKey, cancelBackHold]);

  // Cleanup on unmount
  useEffect(() => () => cancelBackHold(), [cancelBackHold]);

  return (
    <div role="group" aria-label="Tastatur" onTouchStart={NOOP}
      style={{
        padding: '3px 3px 6px', flexShrink: 0,
        display: 'flex', flexDirection: 'column', gap: 4,
        background: '#060604',
      }}>
      {rows.map((row, ri) => (
        <div key={ri} style={{
          display: 'flex', gap: 3,
          paddingLeft: INDENT[ri], paddingRight: INDENT[ri],
        }}>
          {row.map((k, ki) => {
            const sp = 'SHIFT BACK ENTER SPACE NUM ABC'.includes(k.k);
            const shA = k.k === 'SHIFT' && (layout === 'upper' || capsLock);
            const isBack = k.k === 'BACK';
            const handlers = isBack
              ? {
                  onPointerDown: onBackDown,
                  onPointerUp: onBackUp,
                  onPointerLeave: cancelBackHold,
                  onPointerCancel: cancelBackHold,
                  // onClick deliberately omitted — pointerUp handles tap
                }
              : { onClick: () => onKey(k.k) };
            return (
              <button key={`${ri}-${ki}`}
                {...handlers}
                aria-label={
                  isBack ? 'Loeschen (halten = mehr, doppeltap = Wort)' : k.k === 'ENTER' ? 'Senden' :
                  k.k === 'SPACE' ? 'Leertaste' : k.k === 'SHIFT' ?
                    (capsLock ? 'Caps Lock' : 'Grossbuchstaben') :
                  k.k === 'NUM' ? 'Zahlen' : k.k === 'ABC' ? 'Buchstaben' : k.k
                }
                title={isBack ? 'Tap = 1 Zeichen · Halten = mehr · Doppeltap = Wort' : undefined}
                style={{
                  flex: k.f, minHeight: 44,
                  border: '1px solid rgba(223,202,125,.07)', borderRadius: 4,
                  background: shA ? 'rgba(223,202,125,.20)'
                              : sp ? 'rgba(223,202,125,.07)' : 'rgba(223,202,125,.04)',
                  color: '#dfca7d',
                  fontFamily: "'Courier New', monospace",
                  fontSize: k.k.length === 1 ? 16 : 13,
                  fontWeight: k.k.length === 1 ? '400' : '600',
                  cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: 0, outline: 'none', userSelect: 'none',
                  WebkitTapHighlightColor: 'transparent',
                  touchAction: 'manipulation',
                }}>{k.d}</button>
            );
          })}
        </div>
      ))}
    </div>
  );
});

// ═══════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════
function LumosInner() {
  const canvasRef    = useRef(null);
  const chatRef      = useRef(null);
  const endRef       = useRef(null);
  const rafRef       = useRef(null);
  const timerRef     = useRef(null);
  const abortRef     = useRef(null);
  const msgsRef      = useRef([]);    // full message history (mirror of msgs state)
  const textRef      = useRef('');
  const busyRef      = useRef(false);
  const sendRef      = useRef(null);
  const layoutRef    = useRef('lower');
  const capsRef      = useRef(false);
  const shiftTapRef  = useRef(0);
  const msgIdRef     = useRef(0);     // monotonic ID counter (rebased after Load/Import)
  const fpsRef       = useRef({ last: 0, frames: 0, ema: 60 });

  // v1.5: Persistenz-Refs
  const saveTimerRef  = useRef(null);
  const toastTimerRef = useRef(null);
  const fileInputRef  = useRef(null);
  const didLoadRef    = useRef(false); // schuetzt Auto-Save vor leerem ueberschreiben

  const simRef = useRef({
    a: new Float32Array(NCELLS * 3),
    b: new Float32Array(NCELLS * 3),
    imgd: null, u32: null, t: 0, state: ST.IDLE,
    em: new Float32Array(EM_STRIDE * EM_MAX), emN: 0,
  });

  const [msgs, setMsgs]         = useState([]);
  const [text, setText]         = useState('');
  const [busy, setBusy]         = useState(false);
  const [layout, setLayout]     = useState('lower');
  const [capsLock, setCapsLock] = useState(false);
  const [toast, setToast]       = useState(null);
  // v1.6: API-Key + Settings
  const [apiKey, setApiKey]         = useState('');
  const [modelName, setModelName]   = useState(DEFAULT_MODEL);
  const [showSettings, setShowSettings] = useState(false);
  const apiKeyRef    = useRef('');
  const modelNameRef = useRef(DEFAULT_MODEL);
  // v1.7: Extended settings
  const [sysPrompt, setSysPrompt] = useState(SYSTEM);
  const [maxTok, setMaxTok]       = useState(DEFAULT_MAXTOK);
  const [temp, setTemp]           = useState(DEFAULT_TEMP);
  const [streaming, setStreaming] = useState(DEFAULT_STREAM);
  const sysPromptRef = useRef(SYSTEM);
  const maxTokRef    = useRef(DEFAULT_MAXTOK);
  const tempRef      = useRef(DEFAULT_TEMP);
  const streamingRef = useRef(DEFAULT_STREAM);

  // Sync refs for Latest Ref Pattern
  useEffect(() => { msgsRef.current = msgs; }, [msgs]);
  useEffect(() => { busyRef.current = busy; }, [busy]);
  useEffect(() => { layoutRef.current = layout; }, [layout]);
  useEffect(() => { capsRef.current = capsLock; }, [capsLock]);
  useEffect(() => { apiKeyRef.current = apiKey; }, [apiKey]);
  useEffect(() => { modelNameRef.current = modelName; }, [modelName]);
  useEffect(() => { sysPromptRef.current = sysPrompt; }, [sysPrompt]);
  useEffect(() => { maxTokRef.current = maxTok; }, [maxTok]);
  useEffect(() => { tempRef.current = temp; }, [temp]);
  useEffect(() => { streamingRef.current = streaming; }, [streaming]);

  // ─ Text helpers ────────────────────────────────────────────────
  const updateText = useCallback(fn => {
    setText(prev => {
      const next = typeof fn === 'function' ? fn(prev) : fn;
      textRef.current = next;
      return next;
    });
  }, []);
  const appendChar = useCallback(ch => updateText(t => t + ch), [updateText]);
  const backspace  = useCallback(() => updateText(t => t.slice(0, -1)), [updateText]);
  // v1.7.1: Wort löschen (von rechts bis vor letzte Whitespace-Gruppe).
  // Beispiel: "Hallo Welt foo" → backspaceWord() → "Hallo Welt "
  const backspaceWord = useCallback(() => updateText(t => {
    if (!t) return t;
    // strip trailing whitespace, then strip trailing non-whitespace
    const m = t.match(/^(.*?)([\S]+)?(\s*)$/);
    if (!m) return t.slice(0, -1);
    const head = m[1] || '';
    return head;
  }), [updateText]);

  // ─ Emitter ─────────────────────────────────────────────────────
  const addEmitter = useCallback(cfg => {
    const s = simRef.current;
    if (s.emN >= EM_MAX) return;
    const sp = cfg.spread || .35, ei = s.emN * EM_STRIDE;
    s.em[ei]     = GW * .5 + (Math.random() - .5) * GW * sp;
    s.em[ei + 1] = GH * .5 + (Math.random() - .5) * GH * sp;
    s.em[ei + 2] = s.t;
    s.em[ei + 3] = cfg.dur || 5;
    s.em[ei + 4] = cfg.spd || 3.5;
    s.em[ei + 5] = cfg.int || 24;
    s.em[ei + 6] = cfg.dh  || 0;
    s.emN++;
  }, []);

  const burst = useCallback((n, c) => {
    for (let i = 0; i < n; i++) addEmitter({
      ...c,
      dh:  (c.dh  || 0)   + (Math.random() - .5) * 40,
      spd: (c.spd || 3.5) + Math.random() * 2,
    });
  }, [addEmitter]);

  // ─ Message ID helper ──────────────────────────────────────────
  const nextId = useCallback(() => ++msgIdRef.current, []);

  // ─ v1.5: Toast helper ─────────────────────────────────────────
  const showToast = useCallback((msg, type = 'info') => {
    setToast({ msg, type, ts: Date.now() });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  // ─ v1.5: Auto-Load beim Mount ─────────────────────────────────
  useEffect(() => {
    const loaded = loadHistory();
    if (loaded && loaded.length > 0) {
      setMsgs(loaded);
      // ID-Counter rebasen, sonst kollidieren neue IDs mit alten
      const maxId = loaded.reduce((m, x) => x.id > m ? x.id : m, 0);
      msgIdRef.current = maxId;
    }
    didLoadRef.current = true;
  }, []);

  // ─ v1.6/v1.7: API-Key + Modell + erweiterte Settings beim Mount ─
  useEffect(() => {
    const k  = loadApiKey();
    const m  = loadModel();
    const sp = loadSysPrompt(SYSTEM);
    const mt = loadMaxTok();
    const tp = loadTemp();
    const st = loadStream();
    setApiKey(k);
    setModelName(m);
    setSysPrompt(sp);
    setMaxTok(mt);
    setTemp(tp);
    setStreaming(st);
    if (!k) {
      setTimeout(() => setShowSettings(true), 900);
    }
  }, []);

  // ─ v1.7: Settings-Speichern Handler (erweitert) ────────────────
  const handleSaveSettings = useCallback((s) => {
    saveApiKey(s.apiKey);
    saveModel(s.model);
    saveSysPrompt(s.sysPrompt);
    saveMaxTok(s.maxTok);
    saveTemp(s.temp);
    saveStream(s.streaming);
    setApiKey(s.apiKey);
    setModelName(s.model);
    setSysPrompt(s.sysPrompt);
    setMaxTok(s.maxTok);
    setTemp(s.temp);
    setStreaming(s.streaming);
    setShowSettings(false);
    if (s.apiKey) showToast('Einstellungen gespeichert.', 'info');
    else          showToast('Schluessel entfernt.', 'warn');
  }, [showToast]);
  const handleOpenSettings = useCallback(() => setShowSettings(true), []);
  const handleCloseSettings = useCallback(() => setShowSettings(false), []);

  // ─ v1.5: Auto-Save debounced bei msgs-Change ──────────────────
  useEffect(() => {
    if (!didLoadRef.current) return;          // erst nach Load arbeiten
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const persistable = msgs.filter(m => m.role !== 'error');
      if (persistable.length === 0) {
        // Leerer state nach Reset: storage leeren statt leeren payload schreiben
        clearHistory();
        return;
      }
      const res = saveHistory(persistable);
      if (!res.ok && res.reason === 'quota') {
        showToast('Speicher voll. Backup exportieren + Reset empfohlen.', 'warn');
      }
    }, SAVE_DEBOUNCE_MS);
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [msgs, showToast]);

  // ─ v1.5: Reset / Export / Import Handlers ─────────────────────
  const handleReset = useCallback(() => {
    if (msgs.length === 0) { showToast('Schon leer.', 'info'); return; }
    if (typeof window !== 'undefined' && !window.confirm('Alle Lumos-Gespraeche loeschen?\n\nEmpfehlung: vorher Export.')) return;
    setMsgs([]);
    msgIdRef.current = 0;
    clearHistory();
    showToast('Gespraeche geleert.', 'info');
  }, [msgs.length, showToast]);

  const handleExport = useCallback(() => {
    if (msgs.length === 0) { showToast('Keine Gespraeche zum Exportieren.', 'info'); return; }
    try {
      exportToJsonFile(msgs);
      showToast('Backup exportiert.', 'info');
    } catch (err) {
      showToast('Export-Fehler: ' + (err.message || 'unbekannt'), 'warn');
    }
  }, [msgs, showToast]);

  const handleImportClick = useCallback(() => {
    if (fileInputRef.current) fileInputRef.current.click();
  }, []);

  const handleImportFile = useCallback(e => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = parseImportedJson(String(reader.result || ''));
      if (!result.ok) { showToast('Import: ' + result.error, 'warn'); return; }
      if (result.msgs.length === 0) { showToast('Backup enthaelt keine Nachrichten.', 'warn'); return; }
      if (msgsRef.current.length > 0) {
        if (typeof window !== 'undefined' && !window.confirm(`${result.msgs.length} Nachrichten importieren?\n\nAktuelle ${msgsRef.current.length} Nachrichten werden ERSETZT.`)) return;
      }
      setMsgs(result.msgs);
      const maxId = result.msgs.reduce((m, x) => x.id > m ? x.id : m, 0);
      msgIdRef.current = maxId;
      showToast(`${result.msgs.length} Nachrichten importiert.`, 'info');
    };
    reader.onerror = () => showToast('Datei-Lese-Fehler.', 'warn');
    reader.readAsText(file);
    // Input zuruecksetzen, sonst feuert onChange bei gleicher Datei nicht
    e.target.value = '';
  }, [showToast]);

  // ─ Seed simulation ────────────────────────────────────────────
  useEffect(() => {
    const { a } = simRef.current;
    for (let y = 0; y < GH; y++) for (let x = 0; x < GW; x++) {
      const i = (y * GW + x) * 3, n = sn(x * .1, y * .12, Math.random() * 20);
      a[i] = 40 + n * 18; a[i + 1] = 52 + n * 14; a[i + 2] = 10 + Math.abs(n) * 6;
    }
    const ctx = canvasRef.current.getContext('2d', { willReadFrequently: false });
    const imgd = ctx.createImageData(CW, CH);
    simRef.current.imgd = imgd;
    simRef.current.u32 = new Uint32Array(imgd.data.buffer);
  }, []);

  // ─ Animation loop ─────────────────────────────────────────────
  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d', { willReadFrequently: false });
    const tick = now => {
      const s = simRef.current;
      if (!s.imgd) { rafRef.current = requestAnimationFrame(tick); return; }

      const f = fpsRef.current;
      f.frames++;
      if (now - f.last >= 1000) {
        f.ema = f.ema * .7 + f.frames * .3;
        f.frames = 0;
        f.last = now;
      }

      s.t += .02;
      const { a, b, t, state, em, emN } = s;

      for (let y = 0; y < GH; y++)
        for (let x = 0; x < GW; x++)
          stepCell(a, b, (y * GW + x) * 3, x, y, t, state, em, emN);

      s.a = b; s.b = a;

      let nw = 0;
      for (let i = 0; i < s.emN; i++) {
        const ei = i * EM_STRIDE;
        if ((t - em[ei + 2]) < em[ei + 3]) {
          if (nw !== i) {
            const ni = nw * EM_STRIDE;
            for (let k = 0; k < EM_STRIDE; k++) em[ni + k] = em[ei + k];
          }
          nw++;
        }
      }
      s.emN = nw;

      const cur = s.a, u32 = s.u32;
      for (let gy = 0; gy < GH; gy++)
        for (let gx = 0; gx < GW; gx++) {
          const ci = (gy * GW + gx) * 3;
          const px = hslToABGR(cur[ci], cur[ci + 1], cur[ci + 2]);
          const px0 = gx * CX, py0 = gy * CY;
          for (let dy = 0; dy < CY; dy++) {
            let pi = (py0 + dy) * CW + px0;
            for (let dx = 0; dx < CX; dx++) u32[pi++] = px;
          }
        }

      ctx.putImageData(s.imgd, 0, 0);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  // Scroll + cleanup
  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [msgs]);
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (abortRef.current) abortRef.current.abort();
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  // ─ v1.7 Stop-button: cancel laufende Antwort ──────────────────
  const stop = useCallback(() => {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch {}
    }
  }, []);

  // ─ Send (v1.7: Streaming via SSE + Retry-Backoff + erweiterte Settings)
  const send = useCallback(async () => {
    const t = textRef.current.trim();
    if (!t || busyRef.current) return;

    // v1.7: Input-Length-Cap
    if (t.length > INPUT_CAP_CHARS) {
      showToast('Nachricht zu lang (' + t.length + ' / ' + INPUT_CAP_CHARS + ' Zeichen).', 'warn');
      return;
    }

    // v1.6: kein Key → Settings öffnen
    // v1.7.1: zusätzlich sanitize + Format-Check vor jedem fetch.
    // Verhindert die cryptic "non ISO-8859-1 code point" fetch-Exception,
    // die User1 nach Copy-Paste eines E-Mail-Keys mit Curly-Quote bekam.
    const keyRaw = apiKeyRef.current || loadApiKey();
    const key = sanitizeApiKey(keyRaw);
    if (!key) {
      showToast('API-Key fehlt. Im Menue (...) "Einstellungen" oeffnen.', 'warn');
      setShowSettings(true);
      return;
    }
    if (!key.startsWith('sk-ant-')) {
      showToast('API-Key Format falsch. Erwartet "sk-ant-…" — Settings öffnen.', 'warn');
      setShowSettings(true);
      return;
    }
    const mdl  = modelNameRef.current || loadModel() || DEFAULT_MODEL;
    const sys  = sysPromptRef.current  || SYSTEM;
    const mtok = maxTokRef.current     || DEFAULT_MAXTOK;
    const tval = (typeof tempRef.current === 'number') ? tempRef.current : DEFAULT_TEMP;
    const useStream = streamingRef.current !== false;

    textRef.current = ''; setText(''); setBusy(true);
    simRef.current.state = ST.THINK;
    burst(2, { dur: 3, spd: 5, int: 15, dh: 60, spread: .5 });

    const uid = nextId(), aid = nextId();
    const nowIso = new Date().toISOString();
    const userMsg = { id: uid, role: 'user', content: t, timestamp: nowIso };
    const hist = [
      ...msgsRef.current.filter(m => m.content && m.role !== 'error').slice(-API_LIMIT),
      userMsg,
    ];
    setMsgs(p => [...p, userMsg, { id: aid, role: 'assistant', content: '', timestamp: null }]);

    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const classifyErr = (status, body) => {
      if (status === 401) return 'Schluessel ungueltig oder abgelaufen.';
      if (status === 403) return 'Zugriff verweigert (403). Konto-Status pruefen.';
      if (status === 404) return 'Modell unbekannt (404). Anderes Modell waehlen.';
      if (status === 429) return 'Rate-Limit erreicht. Kurz warten.';
      if (status === 500 || status === 503) return 'Anthropic-Server antwortet nicht (' + status + ').';
      if (status === 0)   return 'Netz nicht erreichbar.';
      const apiMsg = body && body.error && body.error.message;
      return apiMsg ? (status + ': ' + apiMsg) : ('HTTP ' + status);
    };

    // v1.7: System mit Prompt-Caching (ephemeral 5min) für günstige Multi-Turn-Chats.
    // Spec: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
    const buildBody = () => ({
      model: mdl,
      max_tokens: mtok,
      temperature: tval,
      system: [{ type: 'text', text: sys, cache_control: { type: 'ephemeral' } }],
      messages: hist.map(m => ({ role: m.role, content: m.content })),
      ...(useStream ? { stream: true } : {}),
    });

    // v1.7: einzelner POST-Versuch (returnt Response oder wirft klassifizierten Error)
    const doFetch = async () => fetch(ANTHROPIC_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': key,
        'anthropic-version': ANTHROPIC_VERSION,
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      signal: ctrl.signal,
      body: JSON.stringify(buildBody()),
    });

    // v1.7: Retry-Backoff für 429 / 503 / overloaded (exponential, max RETRY_MAX)
    const fetchWithRetry = async () => {
      let lastErr = null;
      for (let attempt = 0; attempt <= RETRY_MAX; attempt++) {
        let res;
        try { res = await doFetch(); }
        catch (e) { if (e.name === 'AbortError') throw e; lastErr = e; break; }
        if (res.ok) return res;
        // Status-Klassen die wir retryen
        const retryable = res.status === 429 || res.status === 503 || res.status === 529;
        let body = null;
        try { body = await res.clone().json(); } catch {}
        if (!retryable || attempt === RETRY_MAX) {
          const msg = classifyErr(res.status, body);
          const err = new Error(msg); err._status = res.status; throw err;
        }
        // Backoff: Retry-After-Header beachten falls vorhanden, sonst exponential
        let waitMs = RETRY_BASE_MS * Math.pow(2, attempt);
        const ra = res.headers.get('retry-after');
        if (ra) {
          const sec = parseInt(ra, 10);
          if (Number.isFinite(sec) && sec > 0 && sec < 60) waitMs = sec * 1000;
        }
        showToast('Wiederhole in ' + Math.round(waitMs / 100) / 10 + 's (Versuch ' + (attempt + 2) + '/' + (RETRY_MAX + 1) + ')…', 'warn');
        await new Promise((resolve, reject) => {
          const tid = setTimeout(resolve, waitMs);
          ctrl.signal.addEventListener('abort', () => {
            clearTimeout(tid);
            reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
          }, { once: true });
        });
      }
      if (lastErr) throw lastErr;
      throw new Error('Retry-Loop ohne Resultat');
    };

    const updateAssistant = (content, usage, done) => {
      setMsgs(p => {
        const n = [...p];
        const cur = n[n.length - 1];
        n[n.length - 1] = {
          ...cur,
          id: aid,
          role: 'assistant',
          content,
          usage: usage || cur.usage || null,
          timestamp: done ? new Date().toISOString() : cur.timestamp,
        };
        return n;
      });
    };

    try {
      const res = await fetchWithRetry();

      if (useStream && res.body && typeof res.body.getReader === 'function') {
        // ─ v1.7 SSE-Stream-Parsing ───────────────────────────────
        // Events: message_start | content_block_start | content_block_delta
        //         (text_delta) | content_block_stop | message_delta (stop_reason,
        //         usage.output_tokens) | message_stop | ping | error.
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let text = '';
        let usage = { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 };
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE: events sind durch leerzeile getrennt (\n\n)
          let sep;
          while ((sep = buffer.indexOf('\n\n')) >= 0) {
            const raw = buffer.slice(0, sep); buffer = buffer.slice(sep + 2);
            // Each event has `event:` and `data:` lines. We only need data.
            const dataLines = raw.split('\n').filter(l => l.startsWith('data:'));
            if (dataLines.length === 0) continue;
            const dataStr = dataLines.map(l => l.slice(5).trim()).join('\n');
            if (!dataStr) continue;
            let evt;
            try { evt = JSON.parse(dataStr); } catch { continue; }
            if (evt.type === 'message_start' && evt.message && evt.message.usage) {
              const u = evt.message.usage;
              usage.input_tokens = u.input_tokens || 0;
              usage.cache_creation_input_tokens = u.cache_creation_input_tokens || 0;
              usage.cache_read_input_tokens = u.cache_read_input_tokens || 0;
            } else if (evt.type === 'content_block_delta' && evt.delta && evt.delta.type === 'text_delta') {
              text += evt.delta.text;
              updateAssistant(text, usage, false);
            } else if (evt.type === 'message_delta' && evt.usage) {
              usage.output_tokens = evt.usage.output_tokens || usage.output_tokens;
            } else if (evt.type === 'error') {
              // SSE error event (mid-stream)
              const m = evt.error && evt.error.message ? evt.error.message : 'Stream-Fehler';
              throw new Error(m);
            }
          }
        }
        if (!text) text = '·';
        updateAssistant(text, usage, true);

      } else {
        // ─ Klassisch: Single JSON Response ──────────────────────
        const data = await res.json();
        const reply = (data.content && data.content[0] && data.content[0].text) || '·';
        const u = data.usage || {};
        const usage = {
          input_tokens: u.input_tokens || 0,
          output_tokens: u.output_tokens || 0,
          cache_creation_input_tokens: u.cache_creation_input_tokens || 0,
          cache_read_input_tokens: u.cache_read_input_tokens || 0,
        };
        updateAssistant(reply, usage, true);
      }

      simRef.current.state = ST.SPEAK;
      burst(3, { dur: 6, spd: 4.2, int: 30, dh: 22, spread: .4 });
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => { simRef.current.state = ST.IDLE; }, 7500);

    } catch (err) {
      if (err.name === 'AbortError') {
        // User pressed Stop or new send triggered: keep what's there, mark timestamp
        setMsgs(p => {
          const n = [...p];
          const cur = n[n.length - 1];
          if (cur && cur.role === 'assistant') {
            n[n.length - 1] = { ...cur, timestamp: new Date().toISOString(), content: cur.content || '(abgebrochen)' };
          }
          return n;
        });
        simRef.current.state = ST.IDLE;
        return;
      }
      const netErr = (err.message && /failed to fetch|networkerror|load failed/i.test(err.message))
        ? 'Netz nicht erreichbar / CORS blockiert.'
        : (err.message || 'Fehler');
      setMsgs(p => {
        const n = [...p];
        n[n.length - 1] = { id: aid, role: 'error', content: netErr, timestamp: new Date().toISOString() };
        return n;
      });
      if (err._status === 401) {
        showToast('Schluessel ungueltig. Bitte pruefen.', 'warn');
        setTimeout(() => setShowSettings(true), 400);
      }
      simRef.current.state = ST.IDLE;
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [burst, nextId, showToast]);

  useEffect(() => { sendRef.current = send; }, [send]);

  // ─ Physical keyboard ──────────────────────────────────────────
  useEffect(() => {
    const handler = e => {
      if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'Enter') { e.preventDefault(); sendRef.current?.(); return; }
      // v1.7.1: Ctrl/Alt+Backspace = Wort löschen (Standard Desktop-Verhalten)
      if (e.key === 'Backspace') {
        e.preventDefault();
        if (e.ctrlKey || e.altKey) backspaceWord();
        else backspace();
        return;
      }
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        appendChar(e.key);
        addEmitter({ dur: 1, spd: 10, int: 4, dh: 3, spread: .7 });
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [appendChar, backspace, backspaceWord, addEmitter]);

  // ─ Virtual keyboard handler ───────────────────────────────────
  const onVK = useCallback(key => {
    if (busyRef.current && key !== 'BACK') return;
    tap();
    const now = Date.now();
    const lay = layoutRef.current;
    const caps = capsRef.current;

    switch (key) {
      case 'ENTER': sendRef.current?.(); break;
      case 'BACK':       backspace(); break;
      case 'BACK_WORD':  backspaceWord(); break; // v1.7.1: Doppeltap auf ⌫
      case 'SPACE':
        appendChar(' ');
        addEmitter({ dur: 1, spd: 10, int: 4, dh: 3, spread: .7 });
        break;
      case 'NUM': setLayout('num'); setCapsLock(false); break;
      case 'ABC': setLayout('lower'); setCapsLock(false); break;
      case 'SHIFT':
        if (now - shiftTapRef.current < 400) {
          setCapsLock(p => !p);
          setLayout(p => p === 'upper' ? 'lower' : 'upper');
        } else {
          setLayout(p => p === 'upper' ? 'lower' : 'upper');
          setCapsLock(false);
        }
        shiftTapRef.current = now;
        break;
      default:
        appendChar(key);
        if (lay === 'upper' && !caps) setLayout('lower');
        addEmitter({ dur: 1, spd: 10, int: 4, dh: 3, spread: .7 });
    }
  }, [appendChar, backspace, backspaceWord, addEmitter]);

  // ─ Display messages (capped for DOM perf) ─────────────────────
  const displayMsgs = msgs.length > DISPLAY_CAP ? msgs.slice(-DISPLAY_CAP) : msgs;
  const persistedCount = msgs.filter(m => m.role !== 'error').length;

  // ─── Render ────────────────────────────────────────────────────
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100vh', width: '100vw',
      background: '#040404',
      fontFamily: "'Courier New', Courier, monospace",
      color: '#dfca7d', overflow: 'hidden', userSelect: 'none',
      position: 'relative',
    }}>
      {/* v1.5: hidden file-input fuer Import */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        onChange={handleImportFile}
        style={{ display: 'none' }}
        aria-hidden="true"
      />

      {/* ── Canvas mit Menue + FPS overlay ──────────────────────── */}
      <div aria-hidden="true" style={{
        flex: '0 0 42vh', position: 'relative',
        overflow: 'hidden', background: '#040404',
      }}>
        <canvas ref={canvasRef} width={CW} height={CH} style={{
          width: '100%', height: '100%', display: 'block',
          filter: 'blur(3px) brightness(1.35) saturate(1.1)',
        }} />
        <LumosMenu
          onReset={handleReset}
          onExport={handleExport}
          onImportClick={handleImportClick}
          onSettings={handleOpenSettings}
          msgCount={persistedCount}
          hasKey={!!apiKey}
        />
        <FpsDisplay fpsRef={fpsRef} />
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%,-50%)',
          fontSize: 11, letterSpacing: '.8em',
          color: 'rgba(223,202,125,.07)',
          textTransform: 'uppercase', pointerEvents: 'none',
        }}>lumos</div>
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 28,
          background: 'linear-gradient(transparent, #040404)',
          pointerEvents: 'none',
        }} />
      </div>

      {/* ── Chat ───────────────────────────────────────────────── */}
      <div ref={chatRef} id="lumos-log" role="log"
        aria-label="Lumos Chat" aria-live="polite" aria-atomic="false"
        style={{
          flex: '1 1 0', minHeight: 0, overflowY: 'auto',
          padding: '8px 18px 4px',
          display: 'flex', flexDirection: 'column', gap: 5,
          scrollbarWidth: 'thin',
          scrollbarColor: 'rgba(223,202,125,.04) transparent',
        }}>
        {displayMsgs.length === 0 && (
          <div style={{
            fontSize: 12, color: 'rgba(223,202,125,.12)', fontStyle: 'italic',
          }}>{'·'}</div>
        )}
        {displayMsgs.map(m => (
          <div key={m.id} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '84%',
          }}>
            {m.role === 'user' ? (
              <div style={{
                padding: '4px 10px',
                background: 'rgba(223,202,125,.05)',
                border: '1px solid rgba(223,202,125,.07)',
                fontSize: 12, lineHeight: 1.5, color: '#b89855',
              }}>{m.content}</div>
            ) : m.role === 'error' ? (
              <div role="alert" style={{
                padding: '3px 8px', fontSize: 10, color: '#8a5a3a',
                fontStyle: 'italic',
                borderLeft: '2px solid rgba(180,100,60,.3)',
              }}>{m.content}</div>
            ) : (
              <div style={{
                padding: '1px 0', fontSize: 12.5, lineHeight: 1.7,
                color: '#e8d78c', minHeight: '1em',
              }}>
                {m.content === ''
                  ? <span className="lp">{'···'}</span>
                  : m.content}
                {/* v1.7: Token-Usage-Display (klein, dezent) */}
                {m.usage && (m.usage.input_tokens || m.usage.output_tokens) ? (
                  <div style={{
                    fontSize: 9, color: 'rgba(223,202,125,.28)',
                    marginTop: 3, letterSpacing: '.05em',
                    fontFamily: "'Courier New', monospace",
                  }}>
                    in {m.usage.input_tokens}{m.usage.cache_read_input_tokens ? ' (cache ' + m.usage.cache_read_input_tokens + ')' : ''} · out {m.usage.output_tokens}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} style={{ height: 1, flexShrink: 0 }} />
      </div>

      {/* v1.5: Toast schwebt ueber dem Text-Display */}
      <Toast toast={toast} />

      {/* v1.7: Settings-Modal (API-Key + Modell + SysPrompt + MaxTok + Temp + Streaming) */}
      <SettingsPanel
        open={showSettings}
        apiKey={apiKey}
        modelName={modelName}
        sysPrompt={sysPrompt}
        maxTok={maxTok}
        temp={temp}
        streaming={streaming}
        defaultSysPrompt={SYSTEM}
        hasKey={!!apiKey}
        onSave={handleSaveSettings}
        onClose={handleCloseSettings}
      />

      {/* ── Text display ───────────────────────────────────────── */}
      <div style={{
        padding: '5px 18px', minHeight: 36,
        borderTop: '1px solid rgba(223,202,125,.04)',
        borderBottom: '1px solid rgba(223,202,125,.04)',
        background: 'rgba(223,202,125,.012)',
        display: 'flex', alignItems: 'center', flexShrink: 0,
      }}>
        <div style={{
          flex: 1, fontSize: 13, color: '#dfca7d',
          overflow: 'hidden', whiteSpace: 'nowrap',
          display: 'flex', alignItems: 'center',
        }}>
          <span style={{ opacity: text ? 1 : .3 }}>{text || '·'}</span>
          <span className="cur">|</span>
        </div>
        {busy && <span className="lp" style={{ fontSize: 10, marginLeft: 8 }}>{'···'}</span>}
        {/* v1.7: Stop-Button — sichtbar während laufender Antwort */}
        {busy && (
          <button
            type="button"
            onClick={stop}
            aria-label="Antwort stoppen"
            title="Antwort stoppen"
            style={{
              marginLeft: 10, padding: '3px 9px',
              background: 'rgba(200,90,60,.18)',
              border: '1px solid rgba(200,90,60,.45)',
              color: '#e8a285', fontFamily: "'Courier New', monospace",
              fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase',
              cursor: 'pointer', borderRadius: 0,
            }}
          >Stop</button>
        )}
        {capsLock && <span style={{ fontSize: 8, marginLeft: 8, opacity: .3, letterSpacing: '.2em' }}>CAPS</span>}
      </div>

      {/* ── Keyboard ───────────────────────────────────────────── */}
      <LumosKeyboard onKey={onVK} layout={layout} capsLock={capsLock} />

      {/* ── Styles ─────────────────────────────────────────────── */}
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .lp { opacity: .2; animation: lp 2s ease-in-out infinite; }
        @keyframes lp { 0%, 100% { opacity: .14; } 50% { opacity: .48; } }
        .cur { margin-left: 1px; color: rgba(223,202,125,.45); animation: bk 1s step-end infinite; }
        @keyframes bk { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        button:active { background: rgba(223,202,125,.25) !important; transition: none; }
        ::-webkit-scrollbar { width: 2px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(223,202,125,.04); }
      `}</style>
    </div>
  );
}

// v1.7: ErrorBoundary wraps the whole app — catches render-time failures
export default function Lumos() {
  return (
    <LumosErrorBoundary>
      <LumosInner />
    </LumosErrorBoundary>
  );
}
