"""Price extraction for Amazon.ca product pages."""

from bs4 import BeautifulSoup

OUT_OF_STOCK = "-1"


def extract_price(soup: BeautifulSoup) -> str:
    """Return the price to pay (e.g. '$21.96'), or '-1' when no price is shown."""
    for selector in ("#apex-pricetopay-accessibility-label", "#corePrice_feature_div .a-offscreen"):
        element = soup.select_one(selector)
        price = " ".join(element.get_text(" ", strip=True).split()) if element else ""
        if price.startswith(("$", "CDN$", "C$", "CA$")):
            return price.replace("CDN$", "$", 1).replace("CA$", "$", 1).replace("C$", "$", 1)
    return OUT_OF_STOCK
