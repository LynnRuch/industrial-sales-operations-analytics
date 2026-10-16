
-- ============================================================
-- Industrial Sales Operations Analytics
-- Incremental ERP Staging-to-Core Loader
--
-- Current reporting period: January–September 2026
--
-- Features:
--   - Preserves the validated 2025 baseline
--   - Inserts only transaction IDs missing from core
--   - Detects duplicate source transaction IDs
--   - Detects conflicting existing transactions
--   - Validates counts and revenue
--   - Safe to rerun (idempotent)
--   - Rolls back if any validation fails
--
-- Does not truncate, delete, or update existing records.
-- ============================================================

BEGIN;

-- Prevent concurrent core loads.
LOCK TABLE core.sales_transaction
IN SHARE ROW EXCLUSIVE MODE;

-- Keep the staging source stable during promotion.
LOCK TABLE staging.erp_sales_raw
IN SHARE MODE;

DO $$
DECLARE
    -- Reporting period
    v_start_date DATE := DATE '2026-01-01';
    v_end_date DATE := DATE '2026-10-01';

    -- Validated historical baseline
    v_2025_count BIGINT := 453945;
    v_2025_net NUMERIC(18,2) := 500092428.09;

    -- Validated 2026 source baseline
    v_expected_count BIGINT := 356395;
    v_expected_shipments BIGINT := 355949;
    v_expected_returns BIGINT := 446;
    v_expected_net NUMERIC(18,2) := 392981461.96;

    v_count BIGINT;
    v_shipments BIGINT;
    v_returns BIGINT;
    v_net NUMERIC(18,2);

    v_duplicates BIGINT;
    v_conflicts BIGINT;
    v_inserted BIGINT;
BEGIN

    -- ========================================================
    -- 1. Verify existing 2025 core records
    -- ========================================================

    SELECT
        COUNT(*),
        COALESCE(SUM(posted_sales_amount), 0)
    INTO
        v_count,
        v_net
    FROM core.sales_transaction
    WHERE posting_date >= DATE '2025-01-01'
      AND posting_date < DATE '2026-01-01';

    IF v_count <> v_2025_count
       OR v_net <> v_2025_net
    THEN
        RAISE EXCEPTION
            '2025 core baseline mismatch. Load stopped.';
    END IF;

    -- ========================================================
    -- 2. Validate the selected staging period
    -- ========================================================

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE transaction_type = 'SHIPMENT'
        ),
        COUNT(*) FILTER (
            WHERE transaction_type = 'RETURN'
        ),
        COALESCE(
            SUM(posted_sales_amount::NUMERIC(18,2)),
            0
        )
    INTO
        v_count,
        v_shipments,
        v_returns,
        v_net
    FROM staging.erp_sales_raw
    WHERE posting_date::DATE >= v_start_date
      AND posting_date::DATE < v_end_date;

    IF v_count <> v_expected_count
       OR v_shipments <> v_expected_shipments
       OR v_returns <> v_expected_returns
       OR v_net <> v_expected_net
    THEN
        RAISE EXCEPTION
            'Staging reconciliation failed. Rows: %, Shipments: %, Returns: %, Net: %',
            v_count,
            v_shipments,
            v_returns,
            v_net;
    END IF;

    -- ========================================================
    -- 3. Reject duplicate source transaction IDs
    -- ========================================================

    SELECT COUNT(*)
    INTO v_duplicates
    FROM (
        SELECT TRIM(transaction_id)
        FROM staging.erp_sales_raw
        WHERE posting_date::DATE >= v_start_date
          AND posting_date::DATE < v_end_date
        GROUP BY TRIM(transaction_id)
        HAVING COUNT(*) > 1
    ) duplicates;

    IF v_duplicates <> 0 THEN
        RAISE EXCEPTION
            '% duplicate transaction IDs found in staging.',
            v_duplicates;
    END IF;

    -- ========================================================
    -- 4. Reject conflicting records already in core
    -- ========================================================

    SELECT COUNT(*)
    INTO v_conflicts
    FROM staging.erp_sales_raw s
    JOIN core.sales_transaction c
      ON c.transaction_id = TRIM(s.transaction_id)
    WHERE s.posting_date::DATE >= v_start_date
      AND s.posting_date::DATE < v_end_date
      AND ROW(
          c.transaction_type,
          c.posting_date,
          c.customer_id,
          c.ship_to_id,
          c.product_id,
          c.quantity,
          c.unit_selling_price,
          c.posted_sales_amount
      ) IS DISTINCT FROM ROW(
          TRIM(s.transaction_type),
          s.posting_date::DATE,
          s.customer_id::INTEGER,
          s.ship_to_id::INTEGER,
          s.product_id::INTEGER,
          s.quantity::NUMERIC(14,3),
          s.unit_selling_price::NUMERIC(18,4),
          s.posted_sales_amount::NUMERIC(18,2)
      );

    IF v_conflicts <> 0 THEN
        RAISE EXCEPTION
            '% existing core records conflict with staging.',
            v_conflicts;
    END IF;

    -- ========================================================
    -- 5. Insert only missing transactions
    -- ========================================================

    INSERT INTO core.sales_transaction (
        transaction_id,
        transaction_type,
        posting_date,
        sales_order_number,
        sales_order_line,
        shipment_number,
        shipment_line,
        customer_id,
        ship_to_id,
        product_id,
        quantity,
        unit_selling_price,
        posted_sales_amount,
        currency_code,
        reference_transaction_id,
        source_file_name,
        source_row_number,
        load_batch_id
    )
    SELECT
        NULLIF(TRIM(s.transaction_id), ''),
        TRIM(s.transaction_type),
        s.posting_date::DATE,
        NULLIF(TRIM(s.sales_order_number), ''),
        s.sales_order_line::INTEGER,
        NULLIF(TRIM(s.shipment_number), ''),
        s.shipment_line::INTEGER,
        s.customer_id::INTEGER,
        s.ship_to_id::INTEGER,
        s.product_id::INTEGER,
        s.quantity::NUMERIC(14,3),
        s.unit_selling_price::NUMERIC(18,4),
        s.posted_sales_amount::NUMERIC(18,2),
        TRIM(s.currency_code),
        NULLIF(TRIM(s.reference_transaction_id), ''),
        NULLIF(TRIM(s.source_file_name), ''),
        s.source_row_number::INTEGER,
        NULLIF(TRIM(s.load_batch_id), '')
    FROM staging.erp_sales_raw s
    WHERE s.posting_date::DATE >= v_start_date
      AND s.posting_date::DATE < v_end_date
      AND NOT EXISTS (
          SELECT 1
          FROM core.sales_transaction c
          WHERE c.transaction_id = TRIM(s.transaction_id)
      )
    ORDER BY s.staging_id;

    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    -- ========================================================
    -- 6. Reconcile the completed core reporting period
    -- ========================================================

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE transaction_type = 'SHIPMENT'
        ),
        COUNT(*) FILTER (
            WHERE transaction_type = 'RETURN'
        ),
        COALESCE(SUM(posted_sales_amount), 0)
    INTO
        v_count,
        v_shipments,
        v_returns,
        v_net
    FROM core.sales_transaction
    WHERE posting_date >= v_start_date
      AND posting_date < v_end_date;

    IF v_count <> v_expected_count
       OR v_shipments <> v_expected_shipments
       OR v_returns <> v_expected_returns
       OR v_net <> v_expected_net
    THEN
        RAISE EXCEPTION
            'Core reconciliation failed. Rows: %, Shipments: %, Returns: %, Net: %',
            v_count,
            v_shipments,
            v_returns,
            v_net;
    END IF;

    -- ========================================================
    -- 7. Reconfirm original 2025 baseline
    -- ========================================================

    SELECT
        COUNT(*),
        COALESCE(SUM(posted_sales_amount), 0)
    INTO
        v_count,
        v_net
    FROM core.sales_transaction
    WHERE posting_date >= DATE '2025-01-01'
      AND posting_date < DATE '2026-01-01';

    IF v_count <> v_2025_count
       OR v_net <> v_2025_net
    THEN
        RAISE EXCEPTION
            '2025 core validation failed. Transaction rolled back.';
    END IF;

    RAISE NOTICE
        'PASS: Incremental core load complete. New rows: %',
        v_inserted;

    RAISE NOTICE
        '2026 core: 356395 transactions, $392981461.96 net';

    RAISE NOTICE
        '2025 core preserved: 453945 transactions, $500092428.09 net';

END $$;

COMMIT;
