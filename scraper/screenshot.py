"""Homepage screenshot capture for a business's own website, via Playwright.

Only used against the business's website - never against instagram.com.
"""
import os
from playwright.sync_api import sync_playwright

from utils.logger import get_logger

logger = get_logger()


def capture_homepage_screenshot(url: str, output_dir: str, filename: str, viewport: dict) -> str:
    """Returns the saved screenshot path, or '' on failure."""
    if not url:
        return ""

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
            page.goto(url, timeout=20000, wait_until="load")
            page.screenshot(path=output_path, full_page=False)
            browser.close()
        return output_path
    except Exception as exc:
        logger.warning(f"Screenshot failed for {url}: {exc}")
        return ""
