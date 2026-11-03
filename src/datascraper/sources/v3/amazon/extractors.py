"""Amazon.ca search-result parsing for offer discovery."""

from urllib.parse import urlsplit

from bs4 import BeautifulSoup


def extract_search_candidates(soup: BeautifulSoup, limit: int = 5) -> list[dict[str, str]]:
    """Return {url, title, price, sponsored} for the first `limit` result cards."""
    candidates: list[dict[str, str]] = []
    for card in soup.select("[data-component-type='s-search-result']"):
        heading = card.select_one("a h2")
        link = heading.find_parent("a") if heading else None
        if not link or "/dp/" not in link.get("href", ""):
            continue
        title = heading.get("aria-label") or heading.get_text(" ", strip=True)
        price = card.select_one(".a-price .a-offscreen")
        sponsored = card.select_one(
            ".puis-sponsored-label-text, [aria-label*='Sponsored'], "
            "span[data-component-type='s-sponsored-label']"
        )
        candidates.append(
            {
                "url": "https://www.amazon.ca" + urlsplit(link["href"]).path,
                "title": " ".join(title.split()),
                "price": price.get_text(strip=True) if price else "",
                "sponsored": "true" if sponsored else "false",
            }
        )
        if len(candidates) == limit:
            break
    return candidates
