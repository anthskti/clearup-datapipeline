"""Reusable Chromium session for Amazon.ca price refreshes."""

import logging

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from datascraper.sources.v2.amazon.extractors import extract_price
from datascraper.sources.v3.amazon.shared import is_amazon_block_page

logger = logging.getLogger(__name__)

NAVIGATION_TIMEOUT_MS = 45000
PRODUCT_READY_TIMEOUT_MS = 15000


class AmazonPriceScraper:
    """Keep one Playwright Chromium session alive across the refresh batch."""

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        try:
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                locale="en-CA",
                timezone_id="America/Toronto",
                viewport={"width": 1440, "height": 1000},
            )
        except Exception:
            await self.playwright.stop()
            raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()

    async def scrape_price(self, url: str) -> str:
        """Return the price, or '-1' if the loaded product page shows none (out of stock)."""
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            await page.wait_for_selector("#productTitle", timeout=PRODUCT_READY_TIMEOUT_MS)
            soup = BeautifulSoup(await page.content(), "html.parser")
            if is_amazon_block_page(soup, await page.title()):
                raise ValueError("Amazon returned a robot check or blocked page")
            return extract_price(soup)
        finally:
            await page.close()
