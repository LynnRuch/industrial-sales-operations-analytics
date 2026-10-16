
-- ZIP-based representative ownership
-- One representative per ZIP across all product categories.

CREATE TABLE IF NOT EXISTS core.zip_rep_assignment (
    zip_code VARCHAR(5) PRIMARY KEY,
    rep_id VARCHAR(20) NOT NULL,
    coverage_type VARCHAR(10) NOT NULL,

    CONSTRAINT fk_zip_rep_assignment_zip
        FOREIGN KEY (zip_code)
        REFERENCES core.zip_reference (zip_code),

    CONSTRAINT chk_zip_rep_coverage
        CHECK (coverage_type IN ('Field', 'Inside'))
);
