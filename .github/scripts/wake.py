"""Open the Streamlit app in a real browser, wake it if it is asleep, and wait until the dashboard renders.

A plain HTTP request is not enough: Streamlit Community Cloud answers it with a static page while the app
stays asleep. Only a browser session (or the "get this app back up" button) starts the app.
"""
import os
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "").strip()
if not URL:
    sys.exit("Set the APP_URL repository variable to the app's address, e.g. https://zamp-invoice-agent.streamlit.app")

with sync_playwright() as p:
    try:
        browser = p.chromium.launch(channel="chrome")  # the runner's Google Chrome
    except Exception:
        browser = p.chromium.launch()  # Playwright's own Chromium
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    wake = page.get_by_role("button", name="Yes, get this app back up!")
    try:
        wake.wait_for(timeout=8_000)
        print("App was asleep: waking it")
        wake.click()
    except PlaywrightTimeout:
        print("App was awake")
    # The app itself runs inside an iframe on Streamlit Cloud; wait for its home page text in any frame.
    # Case-insensitive: the page shows some headings in capitals through CSS only.
    markers = ("accounts payable", "purchase orders and their invoices")

    def rendered(frame) -> bool:
        if frame.is_detached():
            return False
        text = frame.content().lower()
        return any(m in text for m in markers)

    for _ in range(36):  # up to about 3 minutes for a cold start
        if any(rendered(f) for f in page.frames):
            print("Dashboard rendered: the app is up")
            break
        page.wait_for_timeout(5_000)
    else:
        browser.close()
        sys.exit("The app did not render within 3 minutes")
    browser.close()
