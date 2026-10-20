"""Playwright Chromium search of Amazon.ca for one product at a time."""

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from datascraper.sources.v3.amazon.extractors import extract_search_candidates
from datascraper.sources.v3.amazon.shared import is_amazon_block_page
from datascraper.taxonomy import capacity_in_text, normalize_product_identity_text

logger = logging.getLogger(__name__)

NAVIGATION_TIMEOUT_MS = 45000
SEARCH_READY_TIMEOUT_MS = 12000


def classify(product: dict[str, str], title: str, url: str = "") -> str:
    """'matched' = brand + exact name + size; 'review' = brand + name words (or size) off; '' = no match."""
    # Amazon titles often omit the brand, but the URL slug usually has it.
    key = normalize_product_identity_text(f"{title} {url.split('/dp/')[0]}")
    brand = normalize_product_identity_text(product["brand"])
    name = normalize_product_identity_text(product["name"])
    words = re.findall(r"[a-z0-9]+", product["name"].casefold())
    if not (brand and name and brand in key and all(word in key for word in words)):
        return ""
    exact_name = name in normalize_product_identity_text(title)
    return "matched" if exact_name and capacity_in_text(product["capacity"], title) else "review"


class AmazonOfferScraper:
    def __init__(self, delay: float = 3.0):
        self.delay = max(0.0, delay)

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        try:
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                locale="en-CA",
                timezone_id="America/Toronto",
                viewport={"width": 1440, "height": 1000},
            )
            self.page = await self.context.new_page()
        except Exception:
            await self.playwright.stop()
            raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()

    async def search(self, product: dict[str, str], limit: int = 5) -> list[dict[str, str]]:
        """Return the top result cards with a `status` each; sponsored cards are never matched."""
        query = " ".join(
            p for p in (product["brand"], product["name"], product["capacity"]) if p and p != "N/A"
        )
        await self.page.goto(
            f"https://www.amazon.ca/s?k={quote_plus(query)}",
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )
        try:
            await self.page.wait_for_selector(
                "[data-component-type='s-search-result']", timeout=SEARCH_READY_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            pass
        soup = BeautifulSoup(await self.page.content(), "html.parser")
        if is_amazon_block_page(soup, await self.page.title()):
            raise ValueError("Amazon returned a robot check or blocked page")
        cards = extract_search_candidates(soup, limit)
        for card in cards:
            card["status"] = "" if card["sponsored"] == "true" else classify(product, card["title"], card["url"])
        return cards
