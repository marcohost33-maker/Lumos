"""Real-browser gate for the web companion's API-key storage (Chromium, file://).

test_web_key_storage.py proves where the source may write the key; the Node test runs the
storage functions against fake storages. Neither sees the browser: the shared file://
localStorage, sessionStorage per tab, the copy into an opener popup, a profile that blocks
site data, or a write through a computed name or an alias. This test loads the shipped
standalone bundle in Chromium and watches the key three ways: a spy on Storage.prototype,
a second tab on the same file:// origin that receives a `storage` event for every
localStorage change (index writes included, which bypass setItem), and a scan of the final
contents. A write the regex cannot see still shows up here.

It runs full Chromium in the new headless mode (channel "chromium"): the headless shell
ignores the profile's content settings, so the blocked-site-data case would pass there for
the wrong reason. Waits are web-first assertions on what the app shows (the menu marks a
missing key with a warning sign) and an explicit storage-event barrier, never fixed sleeps.

Network is blocked for the whole context; only file:// loads. Skips without Playwright or
a Chromium build. Set LUMOS_REQUIRE_BROWSER=1 (the CI web job does) to fail instead.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

BUNDLE = (Path(__file__).resolve().parents[1] / "web" / "v1.7.1"
          / "Lumos-v1.7.1-standalone.html")
NAME = "lumos.apikey.v1"
SECRET = "sk-ant-api03-BROWSERGATE-0000000000000000"
BARRIER = "lumos.test.barrier"
REQUIRED = os.environ.get("LUMOS_REQUIRE_BROWSER") == "1"


def _unavailable(reason: str) -> None:
    if REQUIRED:
        pytest.fail(f"LUMOS_REQUIRE_BROWSER=1 but {reason}")
    pytest.skip(reason)


try:
    from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright
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

# Simulates a browser that refuses ONE storage (SecurityError) for the bundle only, so the
# scenario can still be seeded and watched from the helper pages. A real profile that
# blocks site data refuses both; test_blocked_site_data_* covers that with the real setting.
DENY = """
if (location.pathname.endsWith('standalone.html'))
  Object.defineProperty(window, '%s', {
    get() { throw new DOMException('denied', 'SecurityError'); } });
"""

DUMP = """() => {
  const read = s => { try { return Object.fromEntries(Object.entries(window[s])); }
                      catch (e) { return e.name; } };
  return { local: read('localStorage'), session: read('sessionStorage') };
}"""


@pytest.fixture(scope="module")
def pw():
    if sync_playwright is None:
        _unavailable("playwright is not installed (pip install playwright)")
    p = sync_playwright().start()
    yield p
    p.stop()


@pytest.fixture(scope="module")
def browser(pw):
    try:
        b = pw.chromium.launch(channel="chromium")
    except PlaywrightError as e:
        _unavailable(f"Chromium does not start: {str(e).splitlines()[0]}")
    yield b
    b.close()


def _block_network(ctx) -> None:
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:")
              else r.abort())


class App:
    """The bundle in one page, with what it shows about the key."""

    def __init__(self, page):
        self.page = page
        self.dialog = page.locator('[role="dialog"][aria-label="Einstellungen"]')

    def open(self, reload: bool = False) -> None:
        if reload:
            self.page.reload()
        else:
            self.page.goto(BUNDLE.as_uri())
        expect(self.page.locator('[aria-label="Lumos Chat"]')).to_be_visible()

    def expect_key_loaded(self) -> None:
        # The first menu entry reads "Einstellungen" with a key, "Einstellungen ⚠" without;
        # without a key the settings also open on their own.
        self.page.click('[aria-label="Menue"]')
        expect(self.page.locator('[role="menu"] button').first).to_have_text("Einstellungen")
        self.page.click('[aria-label="Menue"]')
        expect(self.page.locator('[role="menu"]')).to_have_count(0)
        expect(self.dialog).to_have_count(0)

    def expect_asks_for_key(self) -> None:
        expect(self.dialog).to_be_visible()

    def open_settings(self) -> None:
        self.page.click('[aria-label="Menue"]')
        self.page.click('[role="menu"] button >> nth=0')
        expect(self.dialog).to_be_visible()

    def save_key(self, key: str) -> None:
        self.page.fill("#lumos-apikey", key)
        self.dialog.get_by_role("button", name="Speichern").click()
        expect(self.dialog).to_be_hidden()

    def storage(self) -> dict:
        return self.page.evaluate(DUMP)


class Tab:
    """One browser context: the app's tab, a helper page, and a watcher tab."""

    def __init__(self, browser, tmp_path: Path, deny: str | None = None):
        self.helper = tmp_path / "other.html"
        self.helper.write_text("<!doctype html><title>other local file</title>", "utf-8")
        self.writes: list[list] = []
        self.watched: list[list] = []
        self.csp: list[str] = []
        self.errors: list[str] = []
        self._barriers = 0
        self.ctx = browser.new_context()
        _block_network(self.ctx)
        self.ctx.expose_binding("__lumosSpy", lambda _src, w: self.writes.append(w))
        self.ctx.expose_binding("__lumosCsp", lambda _src, v: self.csp.append(v))
        self.ctx.expose_binding("__lumosWatch", lambda _src, w: self.watched.append(w))
        self.ctx.add_init_script(SPY)
        if deny:
            self.ctx.add_init_script(DENY % deny)
        self.watcher = self.new_page(self.helper)
        self.watcher.evaluate(WATCH)
        self.prober = self.new_page(self.helper)
        self.page = self.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.app = App(self.page)

    def new_page(self, at: Path | None = None):
        page = self.ctx.new_page()
        if at is not None:
            page.goto(at.as_uri())
        return page

    def settle(self) -> None:
        """Barrier: every localStorage change made so far has reached the watcher.

        Changes to one storage area reach other documents in order, so once the watcher has
        seen a fresh sentinel written after them, it has seen them too.
        """
        self._barriers += 1
        token = str(self._barriers)
        self.prober.evaluate("([k, t]) => { localStorage.setItem(k, t); localStorage.removeItem(k); }",
                             [BARRIER, token])
        deadline = time.monotonic() + 10
        while [BARRIER, token] not in self.watched:
            assert time.monotonic() < deadline, "storage events did not reach the watcher tab"
            self.watcher.wait_for_timeout(10)  # pumps the binding callbacks

    def seed(self, local: str | None = None, session: str | None = None) -> None:
        self.page.goto(self.helper.as_uri())
        self.page.evaluate(
            "([n, l, s]) => { localStorage.clear(); sessionStorage.clear();"
            " if (l !== null) localStorage.setItem(n, l);"
            " if (s !== null) sessionStorage.setItem(n, s); }", [NAME, local, session])
        self.settle()
        self.writes.clear()
        self.watched.clear()

    def local(self) -> dict:
        # Read through the helper page: it sees the shared file:// localStorage even when a
        # scenario denies the bundle access to it.
        return self.prober.evaluate(DUMP)["local"]

    def check_clean(self) -> None:
        """The invariant every scenario must keep, on top of its own expectations."""
        leaked = [w for w in self.writes if w[3] is not None and SECRET in w[3]
                  and (w[0], w[1], w[2]) != ("session", "setItem", NAME)]
        assert not leaked, f"key written outside sessionStorage[{NAME}]: {leaked}"
        self.settle()
        seen = [w for w in self.watched if w[1] is not None and SECRET in w[1]]
        assert not seen, f"key reached localStorage (seen from another tab): {seen}"
        local = self.local()
        assert not [k for k, v in local.items() if SECRET in v], f"key in localStorage: {local}"
        assert not self.csp, f"CSP violations: {self.csp}"
        assert not self.errors, f"page errors: {self.errors}"

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
        t.app.open(reload=reload)
        t.app.expect_key_loaded()
        got = t.app.storage()
        assert got["session"].get(NAME) == expected, (case, reload, got)
        assert NAME not in got["local"], (case, reload, got)
    if local is not None:
        # Removal of the legacy copy comes before any write of the key.
        ops = [(w[0], w[1]) for w in t.writes if w[2] == NAME]
        assert ops[0] == ("local", "removeItem"), ops
    t.check_clean()


def test_denied_local_storage_keeps_the_session_key(tab) -> None:
    t = tab(deny="localStorage")
    t.seed(session=SECRET)
    t.app.open()
    t.app.expect_key_loaded()
    assert t.app.storage()["session"].get(NAME) == SECRET
    t.check_clean()


def test_denied_session_storage_serves_the_key_from_memory_only(tab) -> None:
    t = tab(deny="sessionStorage")
    t.seed(local=SECRET)
    t.app.open()
    t.app.expect_key_loaded()  # the migrated key serves this page from memory
    assert NAME not in t.local(), "legacy copy must be removed even when the session refuses"
    t.app.open(reload=True)
    t.app.expect_asks_for_key()  # nothing persisted the key
    t.check_clean()


def test_key_entered_in_the_settings_goes_to_session_only(tab) -> None:
    t = tab()
    t.seed()
    t.app.open()
    t.app.expect_asks_for_key()
    t.app.save_key(SECRET)
    t.app.expect_key_loaded()
    assert t.app.storage()["session"].get(NAME) == SECRET
    t.app.open(reload=True)
    t.app.expect_key_loaded()
    assert t.app.storage()["session"].get(NAME) == SECRET
    t.check_clean()


def test_saving_an_empty_key_removes_it(tab) -> None:
    t = tab()
    t.seed(session=SECRET)
    t.app.open()
    t.app.expect_key_loaded()
    t.app.open_settings()
    t.app.save_key("")
    assert NAME not in t.app.storage()["session"]
    t.app.open(reload=True)
    t.app.expect_asks_for_key()
    t.check_clean()


def test_other_tabs_and_noopener_popups_read_nothing(tab) -> None:
    t = tab()
    t.seed(local=SECRET)
    t.app.open()
    t.app.expect_key_loaded()
    other = t.new_page(t.helper)
    assert SECRET not in json.dumps(other.evaluate(DUMP)), "a new tab on another local file sees it"
    with t.page.expect_popup() as info:
        t.page.evaluate("u => { window.open(u, '_blank', 'noopener'); }", t.helper.as_uri())
    popup = info.value
    popup.wait_for_load_state()
    assert SECRET not in json.dumps(popup.evaluate(DUMP)), "a noopener popup sees the key"
    t.check_clean()


def test_residual_risks_documented_in_the_readme_still_hold(tab) -> None:
    """Pins the two residual risks web/v1.7.1/README.md states, so the text stays true.

    If a browser change makes either assertion fail, update the README, not the test.
    """
    t = tab()
    t.seed(session=SECRET)
    t.app.open()
    t.app.expect_key_loaded()
    with t.page.expect_popup() as info:
        t.page.evaluate("u => { window.open(u); }", t.helper.as_uri())
    popup = info.value
    popup.wait_for_load_state()
    assert popup.evaluate(DUMP)["session"].get(NAME) == SECRET, "opener popup gets a session copy"
    t.check_clean()
    t.page.goto(t.helper.as_uri())
    assert t.page.evaluate(DUMP)["session"].get(NAME) == SECRET, "same tab, other file reads it"


# Real "block site data" setting, written into the profile before launch. Chromium then
# refuses both storages with a SecurityError, file:// included (measured 2026-10-22).
def _profile(path: Path, cookies: int) -> Path:
    prefs = path / "Default" / "Preferences"
    prefs.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(prefs.read_text("utf-8")) if prefs.exists() else {}
    data.setdefault("profile", {}).setdefault("default_content_setting_values", {})["cookies"] = cookies
    prefs.write_text(json.dumps(data), "utf-8")
    return path


ALLOW, BLOCK = 1, 2


class Profile:
    """A persistent Chromium profile that is opened, closed and reopened with a setting."""

    def __init__(self, pw, path: Path, helper: Path):
        self.pw, self.path, self.helper = pw, path, helper
        self.ctx = None
        self.errors: list[str] = []

    def launch(self, cookies: int) -> App:
        self.close()
        try:
            self.ctx = self.pw.chromium.launch_persistent_context(
                str(_profile(self.path, cookies)), channel="chromium", headless=True)
        except PlaywrightError as e:
            _unavailable(f"Chromium does not start: {str(e).splitlines()[0]}")
        _block_network(self.ctx)
        page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        return App(page)

    def local(self) -> dict:
        page = self.ctx.new_page()
        page.goto(self.helper.as_uri())
        got = page.evaluate(DUMP)["local"]
        page.close()
        return got

    def close(self) -> None:
        if self.ctx is not None:
            self.ctx.close()
            self.ctx = None


@pytest.fixture
def profile(pw, tmp_path):
    helper = tmp_path / "other.html"
    helper.write_text("<!doctype html><title>other local file</title>", "utf-8")
    p = Profile(pw, tmp_path / "profile", helper)
    yield p
    p.close()


def test_blocked_site_data_keeps_the_key_in_memory_only(profile) -> None:
    app = profile.launch(BLOCK)
    app.open()
    assert app.storage() == {"local": "SecurityError", "session": "SecurityError"}
    app.expect_asks_for_key()
    app.save_key(SECRET)
    app.expect_key_loaded()  # the page works with the key from memory
    app.open(reload=True)
    app.expect_asks_for_key()  # and nothing kept it
    assert not profile.errors, profile.errors
    profile.launch(ALLOW)
    assert NAME not in profile.local(), "a key entered while blocked must not reach the disk"


def test_blocked_site_data_leaves_a_legacy_key_until_storage_is_allowed(profile) -> None:
    """Residual risk: while site data is blocked the app cannot remove an old key.

    The next load with storage allowed migrates it into the session and deletes it.
    """
    app = profile.launch(ALLOW)
    app.page.goto(profile.helper.as_uri())
    app.page.evaluate("([n, k]) => localStorage.setItem(n, k)", [NAME, SECRET])
    app = profile.launch(BLOCK)
    app.open()
    app.expect_asks_for_key()  # the old key is out of reach, not lost
    app = profile.launch(ALLOW)
    assert profile.local().get(NAME) == SECRET, "blocked load must not have touched the disk"
    app.open()
    app.expect_key_loaded()
    assert NAME not in profile.local()
    assert app.storage()["session"].get(NAME) == SECRET
    assert not profile.errors, profile.errors
