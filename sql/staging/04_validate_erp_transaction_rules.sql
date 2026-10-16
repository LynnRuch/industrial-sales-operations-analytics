
-- Industrial Sales Operations Analytics
-- Phase 5: ERP transaction business-rule validation
--
-- Read-only checks. No database changes.
-- Run after staging format and relationship checks pass.

WITH typed AS (
    SELECT
        staging_id,
        transaction_id,
        transaction_type,
        posting_date::DATE AS posting_date,
        customer_id::INTEGER AS customer_id,
        ship_to_id::INTEGER AS ship_to_id,
        product_id::INTEGER AS product_id,
        quantity::NUMERIC(14,3) AS quantity,
        unit_selling_price::NUMERIC(18,4) AS unit_price,
        posted_sales_amount::NUMERIC(18,2) AS amount,
        NULLIF(TRIM(reference_transaction_id), '')
            AS reference_transaction_id
    FROM staging.erp_sales_raw
),

checked AS (
    SELECT
        t.*,
        s.transaction_id AS original_id,
        s.transaction_type AS original_type,
        s.posting_date AS original_posting_date,
        s.customer_id AS original_customer_id,
        s.ship_to_id AS original_ship_to_id,
        s.product_id AS original_product_id,
        s.quantity AS original_quantity,
        s.unit_price AS original_unit_price,

        ROUND(t.quantity * t.unit_price, 2)
            AS expected_amount
    FROM typed t
    LEFT JOIN typed s
        ON t.reference_transaction_id = s.transaction_id
)

SELECT
    COUNT(*) AS total_transactions,

    COUNT(*) FILTER (
        WHERE transaction_type = 'SHIPMENT'
          AND (quantity <= 0 OR unit_price <= 0 OR amount <= 0)
    ) AS invalid_shipments,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND (quantity >= 0 OR unit_price <= 0 OR amount >= 0)
    ) AS invalid_returns,

    COUNT(*) FILTER (
        WHERE amount <> expected_amount
    ) AS amount_mismatches,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND (
              original_id IS NULL
              OR original_type IS DISTINCT FROM 'SHIPMENT'
          )
    ) AS invalid_return_references,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND original_id IS NOT NULL
          AND (
              ABS(quantity) > original_quantity
              OR unit_price IS DISTINCT FROM original_unit_price
          )
    ) AS return_quantity_or_price_mismatches,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND original_id IS NOT NULL
          AND (
              customer_id IS DISTINCT FROM original_customer_id
              OR ship_to_id IS DISTINCT FROM original_ship_to_id
              OR product_id IS DISTINCT FROM original_product_id
          )
    ) AS return_relationship_mismatches,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND original_id IS NOT NULL
          AND posting_date <= original_posting_date
    ) AS invalid_return_posting_dates,

    COUNT(*) FILTER (
        WHERE transaction_type = 'SHIPMENT'
          AND reference_transaction_id IS NOT NULL
    ) AS shipments_with_return_references

FROM checked;
