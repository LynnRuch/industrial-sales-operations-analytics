
-- Industrial Sales Operations Analytics
-- Phase 5: ERP master-data relationship validation
--
-- Read-only validation.
-- No staging or core records are modified.

WITH typed_transactions AS (
    SELECT
        staging_id,
        transaction_id,

        CASE
            WHEN TRIM(customer_id) ~ '^[0-9]{1,9}$'
            THEN customer_id::INTEGER
        END AS customer_id,

        CASE
            WHEN TRIM(ship_to_id) ~ '^[0-9]{1,9}$'
            THEN ship_to_id::INTEGER
        END AS ship_to_id,

        CASE
            WHEN TRIM(product_id) ~ '^[0-9]{1,9}$'
            THEN product_id::INTEGER
        END AS product_id

    FROM staging.erp_sales_raw
),

relationship_checks AS (
    SELECT
        t.staging_id,
        t.transaction_id,

        CASE
            WHEN t.customer_id IS NULL THEN 1
            ELSE 0
        END AS invalid_customer_id,

        CASE
            WHEN t.ship_to_id IS NULL THEN 1
            ELSE 0
        END AS invalid_ship_to_id,

        CASE
            WHEN t.product_id IS NULL THEN 1
            ELSE 0
        END AS invalid_product_id,

        CASE
            WHEN t.customer_id IS NOT NULL
             AND c.customer_id IS NULL THEN 1
            ELSE 0
        END AS unknown_customer,

        CASE
            WHEN t.ship_to_id IS NOT NULL
             AND s.ship_to_id IS NULL THEN 1
            ELSE 0
        END AS unknown_ship_to,

        CASE
            WHEN t.product_id IS NOT NULL
             AND p.product_id IS NULL THEN 1
            ELSE 0
        END AS unknown_product,

        CASE
            WHEN s.ship_to_id IS NOT NULL
             AND t.customer_id IS DISTINCT FROM s.customer_id
            THEN 1
            ELSE 0
        END AS customer_ship_to_mismatch,

        CASE
            WHEN s.ship_to_id IS NOT NULL
             AND z.zip_code IS NULL THEN 1
            ELSE 0
        END AS invalid_ship_to_zip

    FROM typed_transactions t

    LEFT JOIN core.customer c
        ON t.customer_id = c.customer_id

    LEFT JOIN core.ship_to s
        ON t.ship_to_id = s.ship_to_id

    LEFT JOIN core.product p
        ON t.product_id = p.product_id

    LEFT JOIN core.zip_reference z
        ON s.zip_code = z.zip_code
)

SELECT
    COUNT(*) AS total_transactions,

    SUM(invalid_customer_id) AS invalid_customer_ids,
    SUM(invalid_ship_to_id) AS invalid_ship_to_ids,
    SUM(invalid_product_id) AS invalid_product_ids,

    SUM(unknown_customer) AS unknown_customers,
    SUM(unknown_ship_to) AS unknown_ship_tos,
    SUM(unknown_product) AS unknown_products,

    SUM(customer_ship_to_mismatch) AS customer_ship_to_mismatches,
    SUM(invalid_ship_to_zip) AS invalid_ship_to_zips

FROM relationship_checks;
