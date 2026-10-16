
-- Industrial Sales Operations Analytics
-- Phase 5: Promote validated 2025 ERP transactions
--
-- Loads staging.erp_sales_raw into core.sales_transaction.
-- Requires completed staging and business-rule validations.
--
-- Safeguards:
--   1. Refuses to load if core already contains transactions.
--   2. Verifies expected staging counts and net sales.
--   3. Converts source text to typed PostgreSQL values.
--   4. Reconciles core records after insertion.
--   5. Rolls back all inserts if any check fails.

BEGIN;

DO $$
DECLARE
    v_staging_count BIGINT;
    v_core_count BIGINT;
    v_inserted_count BIGINT;
    v_shipment_count BIGINT;
    v_return_count BIGINT;
    v_net_sales NUMERIC(18,2);
BEGIN
    -- Prevent duplicate or accidental repeated loads.
    SELECT COUNT(*)
    INTO v_core_count
    FROM core.sales_transaction;

    IF v_core_count <> 0 THEN
        RAISE EXCEPTION
            'Core already contains % transactions. Load stopped.',
            v_core_count;
    END IF;

    -- Verify the expected staging baseline.
    SELECT
        COUNT(*),
        SUM(posted_sales_amount::NUMERIC(18,2))
    INTO
        v_staging_count,
        v_net_sales
    FROM staging.erp_sales_raw;

    IF v_staging_count <> 453945 THEN
        RAISE EXCEPTION
            'Unexpected staging record count: %',
            v_staging_count;
    END IF;

    IF v_net_sales <> 500092428.09 THEN
        RAISE EXCEPTION
            'Staging net sales reconciliation failed: %',
            v_net_sales;
    END IF;

    -- Promote text values into typed relational columns.
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
        NULLIF(TRIM(transaction_id), ''),
        TRIM(transaction_type),
        posting_date::DATE,
        NULLIF(TRIM(sales_order_number), ''),
        sales_order_line::INTEGER,
        NULLIF(TRIM(shipment_number), ''),
        shipment_line::INTEGER,
        customer_id::INTEGER,
        ship_to_id::INTEGER,
        product_id::INTEGER,
        quantity::NUMERIC(14,3),
        unit_selling_price::NUMERIC(18,4),
        posted_sales_amount::NUMERIC(18,2),
        TRIM(currency_code),
        NULLIF(TRIM(reference_transaction_id), ''),
        NULLIF(TRIM(source_file_name), ''),
        source_row_number::INTEGER,
        NULLIF(TRIM(load_batch_id), '')
    FROM staging.erp_sales_raw
    ORDER BY staging_id;

    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;

    IF v_inserted_count <> 453945 THEN
        RAISE EXCEPTION
            'Inserted % records instead of 453945.',
            v_inserted_count;
    END IF;

    -- Independently reconcile the destination table.
    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE transaction_type = 'SHIPMENT'
        ),
        COUNT(*) FILTER (
            WHERE transaction_type = 'RETURN'
        ),
        SUM(posted_sales_amount)
    INTO
        v_core_count,
        v_shipment_count,
        v_return_count,
        v_net_sales
    FROM core.sales_transaction;

    IF v_core_count <> 453945
       OR v_shipment_count <> 453318
       OR v_return_count <> 627
       OR v_net_sales <> 500092428.09
    THEN
        RAISE EXCEPTION
            'Core reconciliation failed. Count: %, Shipments: %, Returns: %, Net: %',
            v_core_count,
            v_shipment_count,
            v_return_count,
            v_net_sales;
    END IF;

    RAISE NOTICE
        'PASS: % transactions promoted into core.',
        v_inserted_count;

    RAISE NOTICE
        'Shipments: %, Returns: %, Net sales: $%',
        v_shipment_count,
        v_return_count,
        v_net_sales;
END $$;

COMMIT;
