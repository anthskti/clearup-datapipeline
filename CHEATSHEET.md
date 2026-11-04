# Datascraper CLI cheat sheet

Run these commands from the repository root. The CLI does not load `.env`; source it in your shell when a command needs credentials. Files under `inputs/` and `outputs/` are local and gitignored.

## Keep one master catalog

For the initial transition, copy the R2 links from the successful image backfill into the complete skin-type catalog. This keeps failed and imageless rows, and changes only `imageUrls` on unique brand/name matches:

```bash
uv run datascraper catalog apply-images \
  --input outputs/catalog/master_skin_types.csv \
  --images outputs/catalog/r2_backfill.csv \
  --output outputs/catalog/master_candidate.csv
```

Inspect `master_candidate.csv` and the duplicate-key warnings. The current input has 387 rows; four matching brand/name keys are duplicated in the master and stay unchanged for manual review. After reviewing the candidate, make it the ongoing catalog:

```bash
cp outputs/catalog/master_candidate.csv outputs/catalog/master.csv
```

For later batches, append only reviewed `comparison_new.csv` rows to `master.csv` in a CSV editor (without a second header). Leave their `skinTypeSource` blank. Run inference on the full catalog; existing `manual` and `inferred` rows are skipped:

```bash
uv run datascraper enrich skin-types \
  --input outputs/catalog/master.csv \
  --output outputs/catalog/master_enriched.csv
```

Ingest images from the **new-product batch**, not from the full master. Replace the example run path with your batch's `comparison_new.csv`:

```bash
uv run datascraper images ingest \
  --input outputs/runs/yesstyle_skin1004/comparison_new.csv \
  --output outputs/runs/yesstyle_skin1004/image_import.csv \
  --dry-run

uv run datascraper images ingest \
  --input outputs/runs/yesstyle_skin1004/comparison_new.csv \
  --output outputs/runs/yesstyle_skin1004/image_import.csv

uv run datascraper catalog apply-images \
  --input outputs/catalog/master_enriched.csv \
  --images outputs/runs/yesstyle_skin1004/image_import.csv \
  --output outputs/catalog/master_candidate.csv
```

Review the candidate and warnings, then use the `cp` command above to promote it. Keep `master_v1.csv` as the legacy snapshot. Image ingestion outputs only successful rows with images, so rows without a new R2 image remain in the full catalog for separate review before a Clearup import.

## YesStyle: brand page to Clearup product CSV

This example keeps one run in `outputs/runs/yesstyle_skin1004/`. Review each CSV before using it as the next step's input.

### 1. Discover product URLs

Create `inputs/yesstyle/brand_pages.csv` with `brand,listingUrl` columns and a row for the SKIN1004 brand page. Set `APIFY_TOKEN`, then run a bounded crawl:

```bash
uv run datascraper discover yesstyle \
  --input inputs/yesstyle/brand_pages.csv \
  --output outputs/runs/yesstyle_skin1004/product_urls.csv \
  --max-pages 20 --max-depth 3
```

`--max-pages` applies to each brand URL and counts listing and product pages. Increase it if the URL CSV is incomplete. Inspect `product_urls.csv` before scraping; Apify run and dataset details are saved in the adjacent `apify/` folder. Use `--dataset-id ID` to replay a saved dataset for a single brand row without starting another crawl.

### 2. Scrape the discovered pages

```bash
uv run datascraper scrape yesstyle \
  --input outputs/runs/yesstyle_skin1004/product_urls.csv \
  --output outputs/runs/yesstyle_skin1004/products.csv \
  --workers 2 --delay 5
```

Inspect `status`, `price`, and `imageUrls` in `products.csv`. Discovery and scraping append to `run.log` beside their output; add `--log-level DEBUG` when investigating a run.

### 3. Separate new products from catalog matches

Make sure `outputs/catalog/master.csv` reflects the current Clearup catalog, then run:

```bash
uv run datascraper compare catalog \
  --input outputs/runs/yesstyle_skin1004/products.csv \
  --catalog outputs/catalog/master.csv \
  --output-prefix outputs/runs/yesstyle_skin1004/comparison
```

Review all three outputs:

| File | What to do |
| --- | --- |
| `comparison_new.csv` | Review candidates for new Clearup products; this has the normal product import columns. |
| `comparison_existing.csv` | Check matches already represented in the catalog. |
| `comparison_review.csv` | Resolve possible matches, especially size variants, by hand. |

The latter two files include `reviewReason` and matched catalog fields. Do not import the entire scrape or unresolved matches as new products.

### 4. Infer skin types and `skinTypeSource`

Start local Ollama and ensure the default `gemma4:12b-mlx` model is available. First inspect a five-product sample:

```bash
uv run datascraper enrich skin-types \
  --input outputs/runs/yesstyle_skin1004/comparison_new.csv \
  --output outputs/runs/yesstyle_skin1004/products_enriched_sample.csv \
  --limit 5
```

After reviewing the sample, infer the remaining eligible rows by using that output as input and omitting `--limit`:

```bash
uv run datascraper enrich skin-types \
  --input outputs/runs/yesstyle_skin1004/products_enriched_sample.csv \
  --output outputs/runs/yesstyle_skin1004/products_enriched.csv
```

This command fills `skinType` and sets `skinTypeSource=inferred`; there is no separate provenance CLI. Existing `manual` or `inferred` rows are skipped. A limited run still copies deferred rows to its output without inferring them, so use the full output for the next step. On later runs, use the latest enriched CSV as input to preserve provenance; using the original comparison CSV again re-infers rows without provenance. Override the local model with `--model` if needed.

### 5. Replace merchant image URLs with R2 URLs

Set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, and `R2_PUBLIC_BASE_URL`. Preview the image keys first:

```bash
uv run datascraper images ingest \
  --input outputs/runs/yesstyle_skin1004/products_enriched.csv \
  --output outputs/runs/yesstyle_skin1004/products_import.csv \
  --dry-run
```

The dry run does not download, upload, or write `products_import.csv`. To create the Clearup import CSV with R2 URLs:

```bash
uv run datascraper images ingest \
  --input outputs/runs/yesstyle_skin1004/products_enriched.csv \
  --output outputs/runs/yesstyle_skin1004/products_import.csv
```

Inspect `products_import.csv` before handing it to Clearup. Image ingest includes only successful rows with images; compare its row count with `products_enriched.csv` so imageless products are handled separately. The original scraper CSV keeps the merchant image URLs.

## Sephora: scrape an existing URL list

For the maintained Sephora input, run:

```bash
uv run datascraper scrape sephora \
  --input inputs/legacy/sephora_products_v2.csv \
  --output outputs/runs/sephora_manual/products.csv \
  --workers 4 --delay 8
```

Check the output statuses, then compare against the current catalog:

```bash
uv run datascraper compare catalog \
  --input outputs/runs/sephora_manual/products.csv \
  --catalog outputs/catalog/master.csv \
  --output-prefix outputs/runs/sephora_manual/comparison
```

After reviewing `comparison_new.csv` and resolving matches in `comparison_review.csv`, prepare the new-product CSV:

```bash
uv run datascraper enrich skin-types \
  --input outputs/runs/sephora_manual/comparison_new.csv \
  --output outputs/runs/sephora_manual/products_enriched.csv

uv run datascraper images ingest \
  --input outputs/runs/sephora_manual/products_enriched.csv \
  --output outputs/runs/sephora_manual/products_import.csv \
  --dry-run

uv run datascraper images ingest \
  --input outputs/runs/sephora_manual/products_enriched.csv \
  --output outputs/runs/sephora_manual/products_import.csv
```

The last command uploads images to R2. Inspect `products_import.csv` before handing it to Clearup.

## Amazon.ca: find offers for existing Clearup products

Set `CLEARUP_DATABASE_URL` and `CLEARUP_DB_CA_CERT` for the read-only Clearup connection. Search a small brand batch:

```bash
uv run datascraper discover amazon-offers \
  --brand "SKIN1004" --limit 5 \
  --output-prefix outputs/runs/amazon_skin1004/discovery
```

Inspect `discovery_offers.csv` and `discovery_review.csv`. `discovery_candidates.csv` lists checked result cards, and `discovery_unmatched.csv` lists products without a match. The run also updates `outputs/catalog/amazon_offers_master.csv`. Approve an uncertain offer only after checking it, by setting its master row to `status=matched` and `source=manual`. The master is the CSV handoff for reviewed offers.

To refresh matched Amazon URLs in the local master before they are imported into Clearup:

```bash
uv run datascraper refresh prices --master --limit 5 \
  --output outputs/refresh/amazon_refresh.csv
```

This writes both the refresh CSV and updated prices in `amazon_offers_master.csv`. A loaded Amazon page without a price yields `price=-1,stock=false`; a failed page request produces no refresh row.

## Refresh saved Clearup merchant prices

With `CLEARUP_DATABASE_URL` and `CLEARUP_DB_CA_CERT` set, run a small read-only refresh:

```bash
uv run datascraper refresh prices --limit 5 \
  --output outputs/refresh/price_refresh.csv
```

This reads saved YesStyle, Sephora, and Amazon.ca URLs and writes `brand,name,price,merchant,stock` for successful refreshes. It does not update Clearup. Omit `--limit` to refresh all supported listings after checking the sample CSV.

## Backfill merchant images from a legacy catalog CSV

Use this on a CSV that still has original merchant image URLs. The canonical `master.csv` may already have R2 URLs, which the ingest command would treat as new source images. Preview the image keys first:

```bash
uv run datascraper backfill images \
  --input outputs/catalog/master_skin_types.csv \
  --output outputs/catalog/r2_backfill.csv \
  --dry-run
```

With the R2 environment variables set, create the R2-backed CSV:

```bash
uv run datascraper backfill images \
  --input outputs/catalog/master_skin_types.csv \
  --output outputs/catalog/r2_backfill.csv
```

Backfill records upload progress under `outputs/` so a rerun can resume. The dry run does not write `r2_backfill.csv`. Use `catalog apply-images` above to copy its URLs into the complete catalog.

## Command help

```bash
uv run datascraper --help
uv run datascraper discover yesstyle --help
uv run datascraper scrape yesstyle --help
uv run datascraper compare catalog --help
uv run datascraper catalog apply-images --help
uv run datascraper enrich skin-types --help
uv run datascraper images ingest --help
uv run datascraper scrape sephora --help
uv run datascraper discover amazon-offers --help
uv run datascraper refresh prices --help
uv run datascraper backfill images --help
```
