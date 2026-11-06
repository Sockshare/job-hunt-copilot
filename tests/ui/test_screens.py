"""G4 — UI render test (Playwright). Full click-through in No-AI mode; zero console errors; no text leaks; responsive."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SHOTS = ROOT / "docs" / "screenshots"
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None
pytestmark = pytest.mark.skipif(sync_playwright is None, reason="playwright not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    env = {**os.environ, "JOBHUNT_DATA_DIR": str(tmp_path_factory.mktemp("data")), "JOBHUNT_PROVIDER": "offline"}
    proc = subprocess.Popen([sys.executable, "app.py", "--port", str(port), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(80):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _collect(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    # Chrome logs a console line for every non-2xx response; the intentional bad-file 400 is covered by the response hook below.
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)
    page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
    return errors


def _no_leaks(page):
    body = page.inner_text("body")
    for bad in ("undefined", "[object Object]", "NaN"):
        assert bad not in body, bad
    assert not re.search(r"\bnull\b", body)


def test_full_flow(server, browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = _collect(page)
    page.goto(server)
    page.wait_for_selector("#screen-setup:not([hidden])", timeout=10000)
    assert page.locator(".choice").count() == 3
    page.screenshot(path=SHOTS / "01_first_run.png", full_page=True)
    page.click('.choice[data-choice="offline"]')
    page.wait_for_selector("#screen-input:not([hidden])")
    # validation first
    page.click("#matchBtn")
    page.wait_for_selector("#toast:not([hidden])")
    assert "resume" in page.inner_text("#toast").lower()
    page.click("#sampleBtn")
    page.wait_for_function("document.getElementById('resumeText').value.length > 500")
    page.screenshot(path=SHOTS / "02_input.png", full_page=True)
    page.click("#matchBtn")
    page.wait_for_selector("#screen-results:not([hidden])", timeout=15000)
    assert page.inner_text("#scoreNum").endswith("%")
    assert page.locator("#rMatched .kw").count() >= 5 and page.locator("#rMissing .kw").count() >= 1
    assert page.locator("#rAts .ats").count() >= 1
    page.screenshot(path=SHOTS / "03_fit.png", full_page=True)
    # resume pane (checklist in offline mode)
    page.click('.subtab[data-pane="resume"]')
    assert "checklist" in page.inner_text("#tailorHint").lower()
    page.click("#tailorBtn")
    page.wait_for_selector("#tailorChecklist:not([hidden])", timeout=15000)
    assert page.locator("#tailorChecklistItems li").count() >= 1
    page.screenshot(path=SHOTS / "04_resume_checklist.png", full_page=True)
    # letter
    page.click('.subtab[data-pane="letter"]')
    page.fill("#letterDetails", "I am moving to Seattle in January.")
    page.click("#letterBtn")
    page.wait_for_selector("#letterOut:not([hidden])", timeout=15000)
    assert "moving to Seattle" in page.input_value("#letterText")
    page.screenshot(path=SHOTS / "05_letter.png", full_page=True)
    # interview
    page.click('.subtab[data-pane="interview"]')
    assert page.locator("#qRole .qbtn").count() >= 3
    page.click("#gradeBtn", force=True)  # disabled until a question is picked
    page.click("#qBehav .qbtn >> nth=0")
    assert not page.is_disabled("#answerText")
    page.fill("#answerText", "At Brightcart returns went up 18%. I needed to find out why. I pulled the data and found a packaging issue. We changed the box and returns dropped by a third.")
    page.click("#gradeBtn")
    page.wait_for_selector("#gradeOut:not([hidden])", timeout=15000)
    assert "/5" in page.inner_text("#gradeScore")
    page.screenshot(path=SHOTS / "06_interview.png", full_page=True)
    # status + my jobs
    page.select_option("#rStatus", "applied")
    page.wait_for_selector("#toast:not([hidden])")
    page.click("#appsBtn")
    page.wait_for_selector("#modal-apps:not([hidden])")
    assert page.locator(".app-row").count() == 1 and "applied" in page.inner_text(".app-row").lower()
    page.keyboard.press("Escape")
    # settings
    page.click("#settingsBtn")
    page.wait_for_selector("#modal-settings:not([hidden])")
    page.click('input[name=prov][value=gemini]')
    page.click("#setTest")
    page.wait_for_function("document.getElementById('setTestOut').textContent.includes('\u2717')")
    page.click('input[name=prov][value=offline]')
    page.click("#setSave")
    page.wait_for_selector("#modal-settings", state="hidden")
    page.screenshot(path=SHOTS / "07_settings.png")
    # back to input keeps the remembered resume
    page.click("#backBtn")
    page.wait_for_selector("#screen-input:not([hidden])")
    assert len(page.input_value("#resumeText")) > 500
    _no_leaks(page)
    assert errors == [], errors
    page.close()


@pytest.mark.parametrize("width,name", [(1024, "laptop"), (420, "phone")])
def test_responsive(server, browser, width, name):
    page = browser.new_page(viewport={"width": width, "height": 900})
    errors = _collect(page)
    page.goto(server)
    page.wait_for_selector("#screen-input:not([hidden]), #screen-setup:not([hidden])", timeout=10000)
    if page.is_visible("#screen-setup"):
        page.click('.choice[data-choice="offline"]')
        page.wait_for_selector("#screen-input:not([hidden])")
    page.click("#sampleBtn")
    page.wait_for_function("document.getElementById('resumeText').value.length > 500")
    page.click("#matchBtn")
    page.wait_for_selector("#screen-results:not([hidden])", timeout=15000)
    for pane in ("fit", "resume", "letter", "interview"):
        page.click(f'.subtab[data-pane="{pane}"]')
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 2, f"{pane} overflows {overflow}px at {width}px"
    page.screenshot(path=SHOTS / f"08_fit_{name}.png", full_page=True)
    assert errors == [], errors
    page.close()
