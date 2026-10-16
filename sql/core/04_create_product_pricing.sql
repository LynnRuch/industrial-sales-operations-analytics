
-- Industrial Sales Operations Analytics
-- Purpose: Store synthetic reference selling prices by SKU.
-- Transaction selling prices may vary from these base values.

CREATE TABLE IF NOT EXISTS core.product_price_reference (
    product_id          INTEGER PRIMARY KEY,
    base_unit_price     NUMERIC(18, 4) NOT NULL,
    currency_code       CHAR(3) NOT NULL DEFAULT 'USD',

    CONSTRAINT fk_price_product
        FOREIGN KEY (product_id)
        REFERENCES core.product(product_id),

    CONSTRAINT chk_base_unit_price
        CHECK (base_unit_price > 0),

    CONSTRAINT chk_currency_code
        CHECK (currency_code = 'USD')
);