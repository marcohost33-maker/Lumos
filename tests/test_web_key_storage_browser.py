"""Real-browser gate for the web companion's API-key storage (Chromium, file://).

test_web_key_storage.py proves where the source may write the key; the Node test runs the
storage functions against fake storages. Neither sees the browser: the shared file://
localStorage, sessionStorage per tab, the copy into an opener popup, or a write through a
computed name or an alias. This test loads the shipped standalone bundle in Chromium and
watches the key three ways: a spy on Storage.prototype, a second tab on the same file://
origin that receives a `storage` event for every localStorage change (index writes
included, which bypass setItem), and a scan of the final contents. A write the regex cannot
see still shows up here.

Network is blocked for the whole context; only file:// loads. Skips without Playwright or
a Chromium build. Set LUMOS_REQUIRE_BROWSER=1 (the CI web job does) to fail instead.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BUNDLE = (Path(__file__).resolve().parents[1] / "web" / "v1.7.1"
          / "Lumos-v1.7.1-standalone.html")
NAME = "lumos.apikey.v1"
SECRET = "sk-ant-api03-BROWSERGATE-0000000000000000"
REQUIRED = os.environ.get("LUMOS_REQUIRE_BROWSER") == "1"


def _unavailable(reason: str) -> None:
    if REQUIRED:
        pytest.fail(f"LUMOS_REQUIRE_BROWSER=1 but {reason}")
    pytest.skip(reason)


try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:  # pragma: no cover - depends on the environment
    sync_playwright = None

# Records every Storage write and removal (any name) before the app's script runs, and
# reports CSP violations. Replacing the prototype methods also catches
# Storage.prototype.setItem.call(...) and aliased storages; index writes bypass setItem,
# which is what WATCH is for.
SPY = """
(() => {
  for (const m of ['setItem', 'removeItem']) {
    const orig = Storage.prototype[m];
    Storage.prototype[m] = function (...a) {
      let who = 'other';
      try { if (this === window.localStorage) who = 'local'; } catch (e) {}
      try { if (this === window.sessionStorage) who = 'session'; } catch (e) {}
      window.__lumosSpy([who, m, String(a[0]), m === 'setItem' ? String(a[1]) : null]);
      return orig.apply(this, a);
    };
  }
  document.addEventListener('securitypolicyviolation',
    e => window.__lumosCsp(e.violatedDirective + ' ' + e.blockedURI));
})();
"""

# Runs in a second tab: the browser fires `storage` there for every change another document
# makes to the shared localStorage, whatever syntax made it.
WATCH = """
window.addEventListener('storage', e => {
  if (e.storageArea === localStorage) window.__lumosWatch([e.key, e.newValue]);
});
"""

# Simulates a browser that refuses the storage (SecurityError, e.g. blocked site data),
# for the bundle only, so the scenario can still be seeded from the helper page.
DENY = """
if (location.pathname.endsWith('standalone.html'))
  Object.defineProperty(window, '%s', {
    get() { throw new DOMException('denied', 'SecurityError'); } });
"""

DUMP = """() => {
  const read = s => { try { return Object.fromEntries(Object.entries(window[s])); }
                      catch (e) { return null; } };
  return { local: read('localStorage'), session: read('sessionStorage') };
}"""


@pytest.fixture(scope="module")
def browser():
    if sync_playwright is None:
        _unavailable("playwright is not installed (pip install playwright)")
    pw = sync_playwright().start()
    try:
        b = pw.chromium.launch()
    except PlaywrightError as e:
        pw.stop()
        _unavailable(f"Chromium does not start: {str(e).splitlines()[0]}")
    yield b
    b.close()
    pw.stop()


class Tab:
    """One browser context with the spy installed and a helper page to seed storage."""

    def __init__(self, browser, tmp_path: Path, deny: str | None = None):
        self.helper = tmp_path / "other.html"
        self.helper.write_text("<!doctype html><title>other local file</title>", "utf-8")
        self.writes: list[list] = []
        self.watched: list[list] = []
        self.csp: list[str] = []
        self.errors: list[str] = []
        self.ctx = browser.new_context()
        self.ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:")
                       else r.abort())
        self.ctx.expose_binding("__lumosSpy", lambda _src, w: self.writes.append(w))
        self.ctx.expose_binding("__lumosCsp", lambda _src, v: self.csp.append(v))
        self.ctx.expose_binding("__lumosWatch", lambda _src, w: self.watched.append(w))
        self.ctx.add_init_script(SPY)
        if deny:
            self.ctx.add_init_script(DENY % deny)
        self.watcher = self.ctx.new_page()
        self.watcher.goto(self.helper.as_uri())
        self.watcher.evaluate(WATCH)
        self.page = self._track_errors(self.ctx.new_page())

    def _track_errors(self, page):
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        return page

    def seed(self, local: str | None = None, session: str | None = None) -> None:
        self.page.goto(self.helper.as_uri())
        self.page.evaluate(
            "([n, l, s]) => { localStorage.clear(); sessionStorage.clear();"
            " if (l !== null) localStorage.setItem(n, l);"
            " if (s !== null) sessionStorage.setItem(n, s); }", [NAME, local, session])
        self.watcher.wait_for_timeout(100)  # let the seeding events arrive before clearing
        self.writes.clear()
        self.watched.clear()

    def open_app(self, reload: bool = False) -> None:
        if reload:
            self.page.reload()
        else:
            self.page.goto(BUNDLE.as_uri())
        self.page.wait_for_selector('[aria-label="Lumos Chat"]', timeout=10_000)
        # Without a key the app opens its settings after 900 ms; wait past that.
        self.page.wait_for_timeout(1_300)

    def settings_open(self) -> bool:
        return self.page.locator('[role="dialog"][aria-label="Einstellungen"]').count() > 0

    def save_in_ui(self, key: str) -> None:
        self.page.wait_for_selector("#lumos-apikey", timeout=5_000)
        self.page.fill("#lumos-apikey", key)
        self.page.get_by_role("button", name="Speichern").click()
        self.page.wait_for_timeout(200)

    def storage(self, page=None) -> dict:
        return (page or self.page).evaluate(DUMP)

    def check_clean(self) -> None:
        """The invariant every scenario must keep, on top of its own expectations."""
        leaked = [w for w in self.writes if w[3] is not None and SECRET in w[3]
                  and (w[0], w[1], w[2]) != ("session", "setItem", NAME)]
        assert not leaked, f"key written outside sessionStorage[{NAME}]: {leaked}"
        self.watcher.wait_for_timeout(100)
        seen = [w for w in self.watched if w[1] is not None and SECRET in w[1]]
        assert not seen, f"key reached localStorage (seen from another tab): {seen}"
        local = self._real_local()
        assert not [k for k, v in local.items() if SECRET in v], f"key in localStorage: {local}"
        assert not self.csp, f"CSP violations: {self.csp}"
        assert not self.errors, f"page errors: {self.errors}"

    def _real_local(self) -> dict:
        # A second page in the same context reads the shared file:// localStorage even
        # when the scenario denies the bundle access to it.
        probe = self.ctx.new_page()
        probe.goto(self.helper.as_uri())
        local = probe.evaluate(DUMP)["local"]
        probe.close()
        return local

    def close(self) -> None:
        self.ctx.close()


@pytest.fixture
def tab(browser, tmp_path):
    made: list[Tab] = []

    def make(deny: str | None = None) -> Tab:
        made.append(Tab(browser, tmp_path, deny))
        return made[-1]

    yield make
    for t in made:
        t.close()


# id: (seeded localStorage, seeded sessionStorage, expected sessionStorage after load)
SEEDS = {
    "legacy_only": (SECRET, None, SECRET),
    "session_only": (None, SECRET, SECRET),
    "session_and_legacy": (SECRET + "-OLD", SECRET, SECRET),
    "empty_session_value": (SECRET, "", SECRET),
}


@pytest.mark.parametrize("case", SEEDS)
def test_key_ends_up_in_session_only_and_survives_reload(tab, case: str) -> None:
    local, session, expected = SEEDS[case]
    t = tab()
    t.seed(local=local, session=session)
    for reload in (False, True):
        t.open_app(reload=reload)
        got = t.storage()
        assert got["session"].get(NAME) == expected, (case, reload, got)
        assert NAME not in got["local"], (case, reload, got)
        assert not t.settings_open(), "app did not pick up the key"
    if local is not None:
        # Removal of the legacy copy comes before any write of the key.
        ops = [(w[0], w[1]) for w in t.writes if w[2] == NAME]
        assert ops[0] == ("local", "removeItem"), ops
    t.check_clean()


def test_denied_local_storage_keeps_the_session_key(tab) -> None:
    t = tab(deny="localStorage")
    t.seed(session=SECRET)
    t.open_app()
    assert t.storage()["session"].get(NAME) == SECRET
    assert not t.settings_open()
    t.check_clean()


def test_denied_session_storage_serves_the_key_from_memory_only(tab) -> None:
    t = tab(deny="sessionStorage")
    t.seed(local=SECRET)
    t.open_app()
    assert not t.settings_open(), "the migrated key should serve this page from memory"
    assert NAME not in t._real_local(), "legacy copy must be removed even when the session refuses"
    t.open_app(reload=True)
    assert t.settings_open(), "nothing persisted the key, so a reload asks again"
    t.check_clean()


def test_key_entered_in_the_settings_goes_to_session_only(tab) -> None:
    t = tab()
    t.seed()
    t.open_app()
    assert t.settings_open(), "without a key the settings open on their own"
    t.save_in_ui(SECRET)
    assert t.storage()["session"].get(NAME) == SECRET
    t.open_app(reload=True)
    assert t.storage()["session"].get(NAME) == SECRET
    assert not t.settings_open()
    t.check_clean()


def test_saving_an_empty_key_removes_it(tab) -> None:
    t = tab()
    t.seed(session=SECRET)
    t.open_app()
    t.page.click('[aria-label="Menue"]')
    t.page.click('[role="menu"] >> text=Einstellungen')
    t.save_in_ui("")
    assert NAME not in t.storage()["session"]
    t.open_app(reload=True)
    assert t.settings_open()
    t.check_clean()


def test_other_tabs_and_noopener_popups_read_nothing(tab) -> None:
    t = tab()
    t.seed(local=SECRET)
    t.open_app()
    other = t.ctx.new_page()
    other.goto(t.helper.as_uri())
    assert SECRET not in str(t.storage(other)), "a new tab on another local file sees the key"
    with t.page.expect_popup() as info:
        t.page.evaluate("u => { window.open(u, '_blank', 'noopener'); }", t.helper.as_uri())
    popup = info.value
    popup.wait_for_load_state()
    assert SECRET not in str(t.storage(popup)), "a noopener popup sees the key"
    t.check_clean()


def test_residual_risks_documented_in_the_readme_still_hold(tab) -> None:
    """Pins the two residual risks web/v1.7.1/README.md states, so the text stays true.

    If a browser change makes either assertion fail, update the README, not the test.
    """
    t = tab()
    t.seed(session=SECRET)
    t.open_app()
    with t.page.expect_popup() as info:
        t.page.evaluate("u => { window.open(u); }", t.helper.as_uri())
    popup = info.value
    popup.wait_for_load_state()
    assert t.storage(popup)["session"].get(NAME) == SECRET, "opener popup gets a session copy"
    t.page.goto(t.helper.as_uri())
    assert t.storage()["session"].get(NAME) == SECRET, "same tab, other local file reads it"
