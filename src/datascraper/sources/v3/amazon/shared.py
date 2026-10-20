"""Helpers shared by the Amazon.ca v2 refresh and v3 discovery."""

from bs4 import BeautifulSoup


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
