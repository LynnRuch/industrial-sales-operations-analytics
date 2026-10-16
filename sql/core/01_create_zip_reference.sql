-- Industrial Sales Operations Analytics
-- Purpose: Store the validated 2026 ZIP geography reference.
-- Scope: Contiguous 48 states and Washington, DC.
-- Sources: U.S. Census Bureau and GeoNames.

CREATE TABLE IF NOT EXISTS core.zip_reference (
    zip_code       CHAR(5) PRIMARY KEY,
    city           VARCHAR(150) NOT NULL,
    state_name     VARCHAR(100) NOT NULL,
    state_code     CHAR(2) NOT NULL,
    county         VARCHAR(150) NOT NULL,
    latitude       NUMERIC(10, 6) NOT NULL,
    longitude      NUMERIC(10, 6) NOT NULL,

    CONSTRAINT chk_zip_format
        CHECK (zip_code ~ '^[0-9]{5}$'),

    CONSTRAINT chk_latitude
        CHECK (latitude BETWEEN -90 AND 90),

    CONSTRAINT chk_longitude
        CHECK (longitude BETWEEN -180 AND 180)
);