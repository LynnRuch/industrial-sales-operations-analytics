
-- Industrial Sales Operations Analytics
-- Purpose: Define the synthetic industrial product hierarchy.
-- Hierarchy: Category -> Family -> SKU.

CREATE TABLE IF NOT EXISTS core.product_category (
    category_id     INTEGER PRIMARY KEY,
    category_name   VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS core.product_family (
    family_id       INTEGER PRIMARY KEY,
    category_id     INTEGER NOT NULL,
    family_name     VARCHAR(120) NOT NULL,

    CONSTRAINT fk_family_category
        FOREIGN KEY (category_id)
        REFERENCES core.product_category(category_id),

    CONSTRAINT uq_family_name_per_category
        UNIQUE (category_id, family_name)
);

CREATE TABLE IF NOT EXISTS core.product (
    product_id      INTEGER PRIMARY KEY,
    sku             VARCHAR(30) NOT NULL UNIQUE,
    product_name    VARCHAR(200) NOT NULL,
    family_id       INTEGER NOT NULL,
    unit_of_measure VARCHAR(20) NOT NULL,
    active_flag     BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_product_family
        FOREIGN KEY (family_id)
        REFERENCES core.product_family(family_id)
);

CREATE INDEX IF NOT EXISTS idx_product_family
    ON core.product(family_id);
