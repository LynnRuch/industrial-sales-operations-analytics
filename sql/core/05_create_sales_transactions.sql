
-- Industrial Sales Operations Analytics
-- Synthetic ERP posted sales transaction lines.
-- Grain: one posted shipment, return, or price adjustment line.
-- Revenue attribution will use ship-to ZIP territory ownership.

CREATE TABLE IF NOT EXISTS core.sales_transaction (
    transaction_id          VARCHAR(40) PRIMARY KEY,
    transaction_type        VARCHAR(20) NOT NULL,
    posting_date            DATE NOT NULL,

    sales_order_number      VARCHAR(40),
    sales_order_line        INTEGER,
    shipment_number         VARCHAR(40),
    shipment_line           INTEGER,

    customer_id             INTEGER NOT NULL,
    ship_to_id              INTEGER NOT NULL,
    product_id              INTEGER NOT NULL,

    quantity                NUMERIC(14, 3) NOT NULL,
    unit_selling_price      NUMERIC(18, 4) NOT NULL,
    posted_sales_amount     NUMERIC(18, 2) NOT NULL,
    currency_code           CHAR(3) NOT NULL DEFAULT 'USD',

    reference_transaction_id VARCHAR(40),
    source_file_name        VARCHAR(255) NOT NULL,
    source_row_number       INTEGER NOT NULL,
    load_batch_id           VARCHAR(50) NOT NULL,
    loaded_at               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sales_customer
        FOREIGN KEY (customer_id)
        REFERENCES core.customer(customer_id),

    CONSTRAINT fk_sales_ship_to
        FOREIGN KEY (ship_to_id)
        REFERENCES core.ship_to(ship_to_id),

    CONSTRAINT fk_sales_product
        FOREIGN KEY (product_id)
        REFERENCES core.product(product_id),

    CONSTRAINT chk_sales_transaction_type
        CHECK (
            transaction_type IN (
                'SHIPMENT',
                'RETURN',
                'PRICE_CREDIT',
                'PRICE_DEBIT'
            )
        ),

    CONSTRAINT chk_sales_currency
        CHECK (currency_code = 'USD'),

    CONSTRAINT chk_sales_quantity_amount
        CHECK (
            (
                transaction_type = 'SHIPMENT'
                AND quantity > 0
                AND posted_sales_amount > 0
            )
            OR
            (
                transaction_type = 'RETURN'
                AND quantity < 0
                AND posted_sales_amount < 0
            )
            OR
            (
                transaction_type = 'PRICE_CREDIT'
                AND quantity = 0
                AND posted_sales_amount < 0
            )
            OR
            (
                transaction_type = 'PRICE_DEBIT'
                AND quantity = 0
                AND posted_sales_amount > 0
            )
        ),

    CONSTRAINT chk_sales_unit_price
        CHECK (unit_selling_price >= 0),

    CONSTRAINT chk_sales_source_row
        CHECK (source_row_number > 0)
);

CREATE INDEX IF NOT EXISTS idx_sales_posting_date
    ON core.sales_transaction(posting_date);

CREATE INDEX IF NOT EXISTS idx_sales_ship_to
    ON core.sales_transaction(ship_to_id);

CREATE INDEX IF NOT EXISTS idx_sales_product
    ON core.sales_transaction(product_id);
