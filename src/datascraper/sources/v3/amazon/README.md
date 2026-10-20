# Amazon.ca offer discovery (v3)

Finds an Amazon.ca link for products already in Clearup. One Playwright Chromium search per product (`amazon.ca/s?k=brand+name+size`, no Prime filter). Only the top 5 result cards are read; product pages are never opened. Nothing is written to the database.

```bash
uv run datascraper discover amazon-offers --brand "SKIN1004" --limit 30 --output-prefix outputs/runs/amazon_skin1004/discovery
```

Without `--input`, the worklist is read from the read-only Supabase connection (`CLEARUP_DATABASE_URL`, `CLEARUP_DB_CA_CERT`); products that already have an Amazon link there are skipped. `--brand` is case-insensitive, and at least one of `--brand` / `--limit` is required. `--input` takes a `brand,name,capacity` CSV (optional `productId`, `amazonUrl`) instead.

## Matching

Sponsored cards are never matched. For each card:

- `matched`: the exact catalog name is in the title, the brand is in the title or URL slug, and the size matches.
- `review`: brand and every word of the name are present but the exact name or size is off (for example `Asiatica 100` vs `100ml`, or `200ml` vs `6.76 Fluid Ounce`).
- no match: otherwise.

Sizes: `ml`, `oz` / `fl oz`, `g` / `grams`, `pads`, `patches`, compared in the same unit (no ml-to-oz conversion) as whole numbers.

A product takes its first `matched` card, else its first `review` card, else `unmatched`. A blocked or failed search is `error`.

## Output

- Master log: `outputs/catalog/amazon_offers_master.csv`, one row per `productId`: `productId, brand, name, capacity, merchant, website, price, status, source, searchTitle, createdAt, updatedAt`. This is the source of truth and mirrors the backend's `product_merchants` fields.
- Per run (`<prefix>_`): `candidates.csv` (all cards seen), `review.csv`, `unmatched.csv`, and `offers.csv` (`name,brand,merchant,price,website`) for products searched in that run.

Master rules:

- `createdAt` is set once; `updatedAt` changes only when `website`, `price`, `status`, or `searchTitle` change.
- Products already `matched` (auto or manual) are skipped on later runs, which makes runs resumable. Other statuses are searched again. A rerun never overwrites a `matched` row.
- To approve a `review` row, edit it in the master: `status` to `matched`, `source` to `manual` (and `updatedAt` if you want it logged). `source` is `auto` for scripted rows.

## Notes

- Discovery does not set stock or shipping. Price comes from the search card and can be empty (usually out of stock); the backend requires a price, so decide how to handle empty prices at import. `refresh prices` (v2) owns price and stock afterwards.
- The Clearup importer matches by brand and name only, so same-name products with different sizes need a manual look.
- Amazon may block automated access. Blocks are logged as `error` and never bypassed.
- `shared.py` is also used by the v2 Amazon refresh.
