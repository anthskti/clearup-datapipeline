"""Apply image URLs from an ingest CSV to a complete catalog CSV."""

import csv
import logging
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def _read_csv(path: Path, required: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain {', '.join(sorted(required))} columns")
        return list(reader.fieldnames), list(reader)


def _key(row: dict[str, str]) -> tuple[str, str]:
    return (
        (row.get("brand") or "").strip().casefold(),
        (row.get("name") or "").strip().casefold(),
    )


def apply_image_urls(input_csv: Path, images_csv: Path, output_csv: Path) -> Counter[str]:
    """Copy imageUrls onto unique brand/name matches; retain every catalog row."""
    paths = {input_csv.resolve(), images_csv.resolve(), output_csv.resolve()}
    if len(paths) != 3:
        raise ValueError("Input, images, and output CSV paths must be different")

    fields, catalog = _read_csv(input_csv, {"brand", "name", "imageUrls"})
    _, image_rows = _read_csv(images_csv, {"brand", "name", "imageUrls", "status"})
    catalog_counts = Counter(_key(row) for row in catalog)
    images_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()

    for row in image_rows:
        key = _key(row)
        url = (row.get("imageUrls") or "").strip()
        if (
            not all(key)
            or (row.get("status") or "").strip().casefold() != "success"
            or url in {"", "N/A"}
        ):
            counts["invalid_image_rows"] += 1
            continue
        images_by_key[key].add(url)

    for key, urls in images_by_key.items():
        if key not in catalog_counts:
            counts["unmatched_image_keys"] += 1
            logger.warning("Image row has no catalog match: %s / %s", *key)
        elif catalog_counts[key] > 1 or len(urls) > 1:
            counts["ambiguous_keys"] += 1
            logger.warning("Leaving duplicate or conflicting match unchanged: %s / %s", *key)

    for row in catalog:
        key = _key(row)
        urls = images_by_key.get(key)
        if urls and catalog_counts[key] == 1 and len(urls) == 1:
            row["imageUrls"] = next(iter(urls))
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=output_csv.parent,
        prefix=f".{output_csv.name}.",
        suffix=".tmp",
        delete=False,
    ) as output_file:
        temporary_path = Path(output_file.name)
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(catalog)
    os.replace(temporary_path, output_csv)
    logger.info(
        "Catalog image merge: updated=%d unchanged=%d ambiguous_keys=%d unmatched_image_keys=%d invalid_image_rows=%d; output=%s",
        counts["updated"],
        counts["unchanged"],
        counts["ambiguous_keys"],
        counts["unmatched_image_keys"],
        counts["invalid_image_rows"],
        output_csv,
    )
    return counts
