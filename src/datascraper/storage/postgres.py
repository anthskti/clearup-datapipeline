"""Read-only access to Clearup's product and merchant listing rows."""

import os
from pathlib import Path

import psycopg

def fetch_product_merchants(limit: int | None = None) -> list[dict[str, str]]:
    """Fetch refresh candidates using a dedicated read-only PostgreSQL role."""
    database_url = os.environ.get("CLEARUP_DATABASE_URL", "").strip()
    ca_path = os.environ.get("CLEARUP_DB_CA_CERT", "").strip()
    if not database_url:
        raise ValueError("CLEARUP_DATABASE_URL is not set")
    if not ca_path:
        raise ValueError("CLEARUP_DB_CA_CERT must point to the Supabase CA certificate")
    if not Path(ca_path).is_file():
        raise ValueError(f"Supabase CA certificate does not exist: {ca_path}")

    query = """
        SELECT
            pm.id AS product_merchant_id,
            p.name AS name,
            p.brand AS brand,
            COALESCE(to_jsonb(p)->>'capacity', 'N/A') AS capacity,
            pm.price AS price,
            pm.website AS url,
            m.name AS merchant
        FROM public.product_merchants AS pm
        JOIN public.products AS p ON p.id = pm."productId"
        JOIN public.merchants AS m ON m.id = pm."merchantId"
        WHERE pm.website IS NOT NULL AND btrim(pm.website) <> ''
        ORDER BY pm.id
    """
    parameters: tuple[int, ...] = ()
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be at least 1")
        query += " LIMIT %s"
        parameters = (limit,)

    with psycopg.connect(
        database_url,
        sslmode="verify-full",
        sslrootcert=ca_path,
        connect_timeout=10,
        autocommit=True,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            columns = [description.name for description in cursor.description]
            return [
                {
                    key: "" if value is None else str(value)
                    for key, value in zip(columns, row, strict=True)
                }
                for row in cursor.fetchall()
            ]


def fetch_catalog_for_amazon_discovery(
    *, brand: str | None, limit: int | None
) -> list[dict[str, str]]:
    """Read a bounded catalog worklist and mark products already linked to Amazon."""
    database_url = os.environ.get("CLEARUP_DATABASE_URL", "").strip()
    ca_path = os.environ.get("CLEARUP_DB_CA_CERT", "").strip()
    if not database_url:
        raise ValueError("CLEARUP_DATABASE_URL is not set")
    if not ca_path:
        raise ValueError("CLEARUP_DB_CA_CERT must point to the Supabase CA certificate")
    if not Path(ca_path).is_file():
        raise ValueError(f"Supabase CA certificate does not exist: {ca_path}")

    query = """
        WITH catalog AS (
        SELECT
            p.id::text AS product_id,
            COALESCE(p.name, '') AS name,
            COALESCE(p.brand, '') AS brand,
            COALESCE(to_jsonb(p)->>'capacity', 'N/A') AS capacity,
            count(*) OVER (
                PARTITION BY regexp_replace(lower(btrim(COALESCE(p.brand, ''))), '[^[:alnum:]]', '', 'g'),
                             regexp_replace(lower(btrim(COALESCE(p.name, ''))), '[^[:alnum:]]', '', 'g')
            ) AS identity_count,
            EXISTS (
                SELECT 1
                FROM public.product_merchants AS pm
                JOIN public.merchants AS m ON m.id = pm."merchantId"
                WHERE pm."productId" = p.id
                  AND lower(btrim(m.name)) IN ('amazon.ca', 'amazon')
                  AND pm.website IS NOT NULL
                  AND btrim(pm.website) <> ''
            ) AS has_amazon_listing
        FROM public.products AS p
        )
        SELECT product_id, name, brand, capacity, identity_count, has_amazon_listing
        FROM catalog
        WHERE NOT has_amazon_listing
    """
    parameters: list[object] = []
    if brand:
        query += " AND lower(btrim(brand)) = lower(btrim(%s))"
        parameters.append(brand)
    query += " ORDER BY lower(brand), lower(name), product_id"
    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be at least 1")
        query += " LIMIT %s"
        parameters.append(limit)
    with psycopg.connect(
        database_url,
        sslmode="verify-full",
        sslrootcert=ca_path,
        connect_timeout=10,
        autocommit=True,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(parameters))
            columns = [description.name for description in cursor.description]
            return [
                {
                    key: "" if value is None else str(value)
                    for key, value in zip(columns, row, strict=True)
                }
                for row in cursor.fetchall()
            ]
