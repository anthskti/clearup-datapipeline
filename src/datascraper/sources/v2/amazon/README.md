# Amazon.ca price refresh (v2)

Opens a saved Amazon.ca product URL in Playwright Chromium and reads the price from `#apex-pricetopay-accessibility-label` (falling back to `#corePrice_feature_div .a-offscreen`). It does not re-check product identity or Prime eligibility; links are validated by v3 discovery.

- A page with a price returns it (for example `$21.96`).
- A loaded page with no price (out of stock, "See options") returns `-1`; the refresh CSV then has `price=-1,stock=false`.
- A blocked or failed page is a failed refresh and is omitted from the output, preserving the stored price.

Listings come from Clearup's `product_merchants` (read-only), or from the matched rows of `outputs/catalog/amazon_offers_master.csv` with `refresh prices --master`. In master mode the new prices and `updatedAt` are written back to the master. It does not search Amazon or update Clearup directly; out-of-stock products are not searched again here, v3 handles unmatched ones.
