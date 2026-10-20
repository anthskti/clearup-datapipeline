"""Small shared helpers for Amazon.ca offer discovery and price refresh."""

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from datascraper.taxonomy import normalize_product_capacity, normalize_product_identity_text

_ASIN_PATH_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:/|$)", re.IGNORECASE)
_PRICE_RE = re.compile(r"^(?:CDN\$|C\$|CA\$|\$)\s*[\d,]+(?:\.\d{2})?$")


def canonical_amazon_url(raw_url: str) -> str | None:
    """Return a clean Amazon.ca product URL, preserving variant/seller selectors."""
    parts = urlsplit(urljoin("https://www.amazon.ca", raw_url.strip()))
    host = (parts.hostname or "").casefold().rstrip(".")
    if parts.scheme.casefold() not in {"http", "https"}:
        return None
    if host != "amazon.ca" and not host.endswith(".amazon.ca"):
        return None
    match = _ASIN_PATH_RE.search(parts.path)
    if not match:
        return None
    query = parse_qs(parts.query)
    keep = {
        key: query[key][0]
        for key in ("th", "psc", "smid")
        if query.get(key) and query[key][0]
    }
    return urlunsplit(
        ("https", "www.amazon.ca", f"/dp/{match.group(1).upper()}", urlencode(keep), "")
    )


def is_amazon_block_page(soup: BeautifulSoup, title: str = "") -> bool:
    text = f"{title} {soup.get_text(' ', strip=True)}".casefold()
    return any(
        phrase in text
        for phrase in (
            "enter the characters you see below",
            "sorry, we just need to make sure you're not a robot",
            "sorry, we just need to make sure you’re not a robot",
            "automated access to amazon data",
            "robot check",
            "captcha",
        )
    )


def extract_amazon_price(soup: BeautifulSoup) -> str | None:
    selectors = (
        "#corePrice_feature_div .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "#price_inside_buybox",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            value = " ".join(element.get_text(" ", strip=True).split())
            if _PRICE_RE.fullmatch(value):
                return value.replace("CDN$", "$", 1).replace("CA$", "$", 1).replace("C$", "$", 1)
    return None


def has_prime_evidence(soup: BeautifulSoup) -> bool:
    """Require an explicit Prime badge or Prime delivery statement on the offer."""
    for element in soup.select(
        "#primeBadge, #prime-logo, .a-icon-prime, [aria-label*='Prime'], "
        "[data-csa-c-delivery-type='PRIME']"
    ):
        label = " ".join(
            [
                element.get("aria-label", ""),
                element.get("title", ""),
                element.get_text(" ", strip=True),
                " ".join(element.get("class", [])),
            ]
        ).casefold()
        if "prime" in label:
            return True

    for selector in (
        "#deliveryBlockMessage",
        "#deliveryBlockMessage_feature_div",
        "#mir-layout-DELIVERY_BLOCK",
        "#配送",
    ):
        element = soup.select_one(selector)
        text = element.get_text(" ", strip=True).casefold() if element else ""
        if "prime" in text and ("free" in text or "eligible" in text):
            return True
    return False


def extract_amazon_product_details(soup: BeautifulSoup) -> dict[str, str]:
    title_element = soup.select_one("#productTitle")
    title = " ".join(title_element.get_text(" ", strip=True).split()) if title_element else ""

    brand_element = soup.select_one("#bylineInfo")
    brand = " ".join(brand_element.get_text(" ", strip=True).split()) if brand_element else ""
    brand = re.sub(r"^(?:visit the|brand:)\s*", "", brand, flags=re.IGNORECASE).strip()
    brand = re.sub(r"\s*store\s*$", "", brand, flags=re.IGNORECASE).strip()

    details: list[str] = [title]
    for selector in (
        "#variation_size_name .selection",
        "#inline-twister-row-size_name .selection",
        "#inline-twister-row-size_name .a-dropdown-prompt",
        "#variation_style_name .selection",
        "#productOverview_feature_div",
        "#detailBullets_feature_div",
        "#productDetails_feature_div",
    ):
        for element in soup.select(selector):
            text = " ".join(element.get_text(" ", strip=True).split())
            if text:
                details.append(text)

    return {"title": title, "brand": brand, "variant_details": " | ".join(details)}


def matches_amazon_product(
    *,
    expected_brand: str,
    expected_name: str,
    expected_capacity: str,
    details: dict[str, str],
    require_capacity: bool = True,
) -> tuple[bool, str]:
    title_key = normalize_product_identity_text(details.get("title", ""))
    brand_key = normalize_product_identity_text(expected_brand)
    actual_brand_key = normalize_product_identity_text(details.get("brand", ""))
    name_key = normalize_product_identity_text(expected_name)
    content_key = normalize_product_identity_text(details.get("variant_details", ""))

    if not brand_key or not (brand_key in actual_brand_key or brand_key in title_key):
        return False, "brand_not_verified"
    if not name_key:
        return False, "product_name_not_verified"
    if name_key not in title_key:
        if SequenceMatcher(None, name_key, title_key).ratio() >= 0.75:
            return False, "similar_product_name_needs_review"
        return False, "product_name_not_verified"

    capacity_key = normalize_product_capacity(expected_capacity)
    if not capacity_key or capacity_key.casefold() in {"na", "n/a", "none", "-"}:
        if require_capacity:
            return False, "catalog_capacity_missing"
        return True, "verified_without_capacity"
    actual_content = normalize_product_capacity(content_key)
    if capacity_key not in actual_content:
        return False, "capacity_or_variant_not_verified"
    return True, "verified"
