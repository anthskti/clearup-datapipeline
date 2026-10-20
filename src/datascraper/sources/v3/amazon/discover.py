"""Find Amazon.ca offers for products already in Clearup and log them in a master CSV."""

import asyncio
import csv
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from datascraper.sources.v3.amazon.scraper import AmazonOfferScraper
from datascraper.storage.postgres import fetch_catalog_for_amazon_discovery
from datascraper.taxonomy import normalize_product_identity_text

logger = logging.getLogger(__name__)

MASTER_PATH = Path(__file__).resolve().parents[5] / "outputs" / "catalog" / "amazon_offers_master.csv"
MASTER_FIELDS = [
    "productId", "brand", "name", "capacity", "merchant", "website", "price",
    "status", "source", "searchTitle", "createdAt", "updatedAt",
]
CANDIDATE_FIELDS = ["productId", "brand", "name", "capacity", "status", "title", "price", "sponsored", "url"]
OFFER_FIELDS = ["name", "brand", "merchant", "price", "website"]
_NO_LINK = {"", "false", "0", "no", "n/a", "none"}
_MASTER_VALUES = ("website", "price", "status", "source", "searchTitle")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_worklist(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path)
    if not rows or not {"brand", "name", "capacity"} <= {k.strip().casefold() for k in rows[0]}:
        raise ValueError("Amazon discovery input CSV needs brand,name,capacity columns")
    rows = [{k.strip().casefold(): (v or "").strip() for k, v in row.items()} for row in rows]
    return [
        {
            "product_id": row.get("productid") or str(number),
            "brand": row["brand"],
            "name": row["name"],
            "capacity": row["capacity"] or "N/A",
            "has_amazon_listing": row.get("amazonurl", ""),
        }
        for number, row in enumerate(rows, start=2)
    ]


async def discover_amazon_offers(
    *,
    output_prefix: Path,
    brand: str | None = None,
    limit: int | None = None,
    input_csv: Path | None = None,
    max_candidates: int = 5,
    delay: float = 3.0,
) -> dict[str, int]:
    """Search a bounded worklist; write per-run CSVs and upsert the master log."""
    if not brand and limit is None:
        raise ValueError("Provide --brand, --limit, or both to bound Amazon discovery")
    if limit is not None and limit < 1:
        raise ValueError("--limit must be at least 1")

    rows = (
        _read_worklist(input_csv)
        if input_csv
        else fetch_catalog_for_amazon_discovery(brand=brand, limit=limit)
    )
    brand_key = normalize_product_identity_text(brand) if brand else ""
    master = {row["productId"]: row for row in _read_csv(MASTER_PATH)}
    worklist = [
        row
        for row in rows
        if row.get("has_amazon_listing", "").strip().casefold() in _NO_LINK
        and (not brand_key or normalize_product_identity_text(row["brand"]) == brand_key)
        # Resume: products already matched (auto or manual) are never searched again.
        and master.get(row["product_id"], {}).get("status") != "matched"
    ][:limit]
    logger.info("Amazon offer discovery worklist: %d products", len(worklist))

    candidates: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    async with AmazonOfferScraper(delay=delay) as scraper:
        for index, product in enumerate(worklist, start=1):
            logger.info("Searching Amazon.ca %d/%d: %s", index, len(worklist), product["name"])
            try:
                cards = await scraper.search(product, max_candidates)
            except Exception as exc:
                logger.warning("Amazon search failed for %s: %s", product["product_id"], exc)
                cards = []
                best = {"status": "error", "url": "", "price": "", "title": str(exc)}
            else:
                best = next(
                    (c for want in ("matched", "review") for c in cards if c["status"] == want),
                    {"status": "unmatched", "url": "", "price": "", "title": ""},
                )
            counts[best["status"]] += 1
            candidates.extend(
                {"productId": product["product_id"], **product, **card} for card in cards
            )

            new = {
                "productId": product["product_id"],
                "brand": product["brand"],
                "name": product["name"],
                "capacity": product["capacity"],
                "merchant": "Amazon",
                "website": best["url"],
                "price": best["price"],
                "status": best["status"],
                "source": "auto",
                "searchTitle": best["title"],
            }
            old = master.get(product["product_id"])
            if old is None:
                master[product["product_id"]] = {**new, "createdAt": now, "updatedAt": now}
            elif any(old.get(k) != new[k] for k in _MASTER_VALUES):
                master[product["product_id"]] = {**old, **new, "updatedAt": now}
            await asyncio.sleep(scraper.delay)

    _write_csv(MASTER_PATH, MASTER_FIELDS, list(master.values()))
    searched = {p["product_id"] for p in worklist}
    prefix = output_prefix

    def per_run(status: str) -> list[dict[str, str]]:
        return [r for r in master.values() if r["status"] == status and r["productId"] in searched]

    _write_csv(prefix.with_name(f"{prefix.name}_candidates.csv"), CANDIDATE_FIELDS, candidates)
    _write_csv(prefix.with_name(f"{prefix.name}_review.csv"), MASTER_FIELDS, per_run("review"))
    _write_csv(prefix.with_name(f"{prefix.name}_unmatched.csv"), MASTER_FIELDS, per_run("unmatched"))
    _write_csv(prefix.with_name(f"{prefix.name}_offers.csv"), OFFER_FIELDS, per_run("matched"))
    logger.info("Amazon offer discovery complete: %s; master=%s", dict(counts), MASTER_PATH)
    return dict(counts)
