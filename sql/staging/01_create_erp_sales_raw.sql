
-- Industrial Sales Operations Analytics
-- Phase 5: Raw ERP transaction staging
--
-- All incoming CSV fields are stored as TEXT.
-- Data types and business rules are validated before
-- records are promoted into core.sales_transaction.

CREATE TABLE IF NOT EXISTS staging.erp_sales_raw (
    staging_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    transaction_id TEXT,
    transaction_type TEXT,
    posting_date TEXT,

    sales_order_number TEXT,
    sales_order_line TEXT,
    shipment_number TEXT,
    shipment_line TEXT,

    customer_id TEXT,
    ship_to_id TEXT,
    product_id TEXT,

    quantity TEXT,
    unit_selling_price TEXT,
    posted_sales_amount TEXT,
    currency_code TEXT,

    reference_transaction_id TEXT,

    source_file_name TEXT,
    source_row_number TEXT,
    load_batch_id TEXT,

    staged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE staging.erp_sales_raw IS
    'Unvalidated ERP transaction records preserved for data quality checks and promotion into core.';

COMMENT ON COLUMN staging.erp_sales_raw.staging_id IS
    'Unique identifier assigned when a source record enters staging.';

COMMENT ON COLUMN staging.erp_sales_raw.staged_at IS
    'Timestamp when the source record was inserted into staging.';
