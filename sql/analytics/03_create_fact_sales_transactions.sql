
-- ============================================================
-- Industrial Sales Operations Analytics
-- Analytics Sales Transaction Fact View
--
-- Source of truth: core.sales_transaction
-- Reporting period: January 2025–September 2026
--
-- Territory attribution:
--   Ship-to ZIP determines the assigned sales rep.
--   Both years use the current ZIP assignment structure.
--
-- Safe to rerun.
-- Does not change source transactions or territory data.
-- ============================================================

BEGIN;

CREATE OR REPLACE VIEW analytics.fact_sales_transactions AS
SELECT
    -- Transaction identity
    s.transaction_id,
    s.transaction_type,
    s.reference_transaction_id,

    -- Date relationship
    d.date_key,
    s.posting_date,
    d.calendar_year,
    d.calendar_quarter,
    d.calendar_month,
    d.year_month,

    -- Customer relationships
    s.customer_id,
    s.ship_to_id,

    -- Shipping location and territory ownership
    st.zip_code AS ship_to_zip_code,
    za.rep_id AS assigned_rep_id,
    za.coverage_type,

    -- Product relationship
    s.product_id,

    -- Transaction financials
    s.quantity,
    s.unit_selling_price,
    s.posted_sales_amount AS net_sales_amount,

    -- Source traceability
    s.sales_order_number,
    s.sales_order_line,
    s.shipment_number,
    s.shipment_line,
    s.source_file_name,
    s.source_row_number,
    s.load_batch_id

FROM core.sales_transaction s

LEFT JOIN analytics.dim_date d
    ON s.posting_date = d.calendar_date

LEFT JOIN core.ship_to st
    ON s.ship_to_id = st.ship_to_id

LEFT JOIN core.zip_rep_assignment za
    ON st.zip_code = za.zip_code;

-- ============================================================
-- Validate the reporting view
-- ============================================================

DO $$
DECLARE
    v_count BIGINT;
    v_distinct_transactions BIGINT;
    v_net_sales NUMERIC(18,2);
    v_missing_dates BIGINT;
    v_missing_reps BIGINT;
    v_customer_mismatches BIGINT;
BEGIN

    SELECT
        COUNT(*),
        COUNT(DISTINCT transaction_id),
        COALESCE(SUM(net_sales_amount), 0),

        COUNT(*) FILTER (
            WHERE date_key IS NULL
        ),

        COUNT(*) FILTER (
            WHERE assigned_rep_id IS NULL
        )

    INTO
        v_count,
        v_distinct_transactions,
        v_net_sales,
        v_missing_dates,
        v_missing_reps

    FROM analytics.fact_sales_transactions;

    IF v_count <> 810340 THEN
        RAISE EXCEPTION
            'Fact view count mismatch: % rows.',
            v_count;
    END IF;

    IF v_distinct_transactions <> v_count THEN
        RAISE EXCEPTION
            'Fact view contains duplicate transaction IDs.';
    END IF;

    IF v_net_sales <> 893073890.05 THEN
        RAISE EXCEPTION
            'Fact view revenue mismatch: %.',
            v_net_sales;
    END IF;

    IF v_missing_dates <> 0 THEN
        RAISE EXCEPTION
            '% transactions have no date dimension match.',
            v_missing_dates;
    END IF;

    IF v_missing_reps <> 0 THEN
        RAISE EXCEPTION
            '% transactions have no assigned rep.',
            v_missing_reps;
    END IF;

    SELECT COUNT(*)
    INTO v_customer_mismatches
    FROM analytics.fact_sales_transactions f
    JOIN core.ship_to st
        ON f.ship_to_id = st.ship_to_id
    WHERE f.customer_id <> st.customer_id;

    IF v_customer_mismatches <> 0 THEN
        RAISE EXCEPTION
            '% customer/ship-to relationships are inconsistent.',
            v_customer_mismatches;
    END IF;

    RAISE NOTICE
        'PASS: Fact view contains % transactions.',
        v_count;

    RAISE NOTICE
        'PASS: Net revenue reconciles to $%.',
        v_net_sales;

    RAISE NOTICE
        'PASS: All transactions have dates and assigned reps.';

END $$;

COMMIT;

-- ============================================================
-- Display annual reporting totals
-- ============================================================

SELECT
    calendar_year,
    COUNT(*) AS transaction_count,
    COUNT(*) FILTER (
        WHERE transaction_type = 'SHIPMENT'
    ) AS shipment_count,
    COUNT(*) FILTER (
        WHERE transaction_type = 'RETURN'
    ) AS return_count,
    SUM(net_sales_amount) AS net_sales
FROM analytics.fact_sales_transactions
GROUP BY calendar_year
ORDER BY calendar_year;
