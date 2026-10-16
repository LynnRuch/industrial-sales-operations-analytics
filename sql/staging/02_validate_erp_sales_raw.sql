
-- Industrial Sales Operations Analytics
-- Phase 5: ERP staging data-quality validation
--
-- Read-only checks. No records are modified.

SELECT
    COUNT(*) AS total_records,

    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(transaction_id), '') IS NULL
    ) AS missing_transaction_ids,

    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(posting_date), '') IS NULL
    ) AS missing_posting_dates,

    COUNT(*) FILTER (
        WHERE NULLIF(TRIM(customer_id), '') IS NULL
           OR NULLIF(TRIM(ship_to_id), '') IS NULL
           OR NULLIF(TRIM(product_id), '') IS NULL
    ) AS missing_business_keys,

    COUNT(*) FILTER (
        WHERE transaction_type NOT IN ('SHIPMENT', 'RETURN')
           OR transaction_type IS NULL
    ) AS invalid_transaction_types,

    COUNT(*) FILTER (
        WHERE quantity IS NULL
           OR TRIM(quantity) !~ '^-?[0-9]+(\.[0-9]{1,3})?$'
    ) AS invalid_quantities,

    COUNT(*) FILTER (
        WHERE unit_selling_price IS NULL
           OR TRIM(unit_selling_price) !~ '^[0-9]+(\.[0-9]{1,4})?$'
    ) AS invalid_unit_prices,

    COUNT(*) FILTER (
        WHERE posted_sales_amount IS NULL
           OR TRIM(posted_sales_amount) !~ '^-?[0-9]+(\.[0-9]{1,2})?$'
    ) AS invalid_sales_amounts,

    COUNT(*) FILTER (
        WHERE currency_code IS DISTINCT FROM 'USD'
    ) AS invalid_currencies,

    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
          AND NULLIF(TRIM(reference_transaction_id), '') IS NULL
    ) AS returns_missing_references

FROM staging.erp_sales_raw;


-- Identify duplicate transaction IDs without changing records.

SELECT
    transaction_id,
    COUNT(*) AS duplicate_count
FROM staging.erp_sales_raw
GROUP BY transaction_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, transaction_id;
