
-- Industrial Sales Operations Analytics
-- Purpose: Define parent customers and physical ship-to locations.
-- All customer and ship-to data will be synthetic.

CREATE TABLE IF NOT EXISTS core.customer (
    customer_id       INTEGER PRIMARY KEY,
    customer_name     VARCHAR(200) NOT NULL,
    industry          VARCHAR(100) NOT NULL,
    customer_segment  VARCHAR(50) NOT NULL,
    created_date      DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS core.ship_to (
    ship_to_id        INTEGER PRIMARY KEY,
    customer_id       INTEGER NOT NULL,
    ship_to_name      VARCHAR(200) NOT NULL,
    zip_code          CHAR(5) NOT NULL,
    facility_type     VARCHAR(100) NOT NULL,
    active_flag       BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_ship_to_customer
        FOREIGN KEY (customer_id)
        REFERENCES core.customer(customer_id),

    CONSTRAINT fk_ship_to_zip
        FOREIGN KEY (zip_code)
        REFERENCES core.zip_reference(zip_code)
);

CREATE INDEX IF NOT EXISTS idx_ship_to_customer
    ON core.ship_to(customer_id);

CREATE INDEX IF NOT EXISTS idx_ship_to_zip
    ON core.ship_to(zip_code);
