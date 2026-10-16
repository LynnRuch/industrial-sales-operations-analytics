-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- Reporting Dimensions for Power BI
--
-- Source: Existing core master, ZIP assignment,
--         and sales organization tables.
--
-- Creates four reporting views:
--   dim_customer
--   dim_ship_to
--   dim_product
--   dim_sales_rep
--
-- Sales representative dimension now includes:
--   Fictional representative names
--   Geographic management hierarchy
--   Power BI display labels
--
-- Existing validated core data is not modified.
-- Safe to rerun.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. PARENT CUSTOMER DIMENSION
-- ============================================================

CREATE OR REPLACE VIEW analytics.dim_customer AS
SELECT
    c.customer_id,
    c.customer_name,
    c.industry,
    c.customer_segment,
    c.created_date
FROM core.customer c;


-- ============================================================
-- 2. SHIP-TO FACILITY DIMENSION
--
-- Each facility has exactly one parent customer.
-- ZIP ownership determines sales representative.
-- Current ZIP assignments apply to both sales years.
-- ============================================================

CREATE OR REPLACE VIEW analytics.dim_ship_to AS
SELECT
    st.ship_to_id,
    st.customer_id,
    st.ship_to_name,
    TRIM(st.zip_code) AS zip_code,
    st.facility_type,
    st.active_flag,
    za.rep_id AS assigned_rep_id,
    za.coverage_type
FROM core.ship_to st
LEFT JOIN core.zip_rep_assignment za
    ON TRIM(st.zip_code) = za.zip_code;


-- ============================================================
-- 3. PRODUCT DIMENSION
--
-- Hierarchy:
-- Category -> Family -> SKU
-- ============================================================

CREATE OR REPLACE VIEW analytics.dim_product AS
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.unit_of_measure,
    p.active_flag,

    pf.family_id,
    pf.family_name,

    pc.category_id,
    pc.category_name

FROM core.product p

JOIN core.product_family pf
    ON p.family_id = pf.family_id

JOIN core.product_category pc
    ON pf.category_id = pc.category_id;


-- ============================================================
-- 4. SALES REPRESENTATIVE DIMENSION
--
-- Original territory attributes are preserved:
--   rep_id
--   coverage_type
--   assigned_zip_count
--
-- Organization attributes are added from the validated
-- fictional sales organization hierarchy.
--
-- Every representative must have exactly one manager.
--
-- Hierarchy:
-- Management Region -> Sales Manager -> Sales Rep
--
-- No ZIP assignments or transactions are changed.
-- ============================================================

CREATE OR REPLACE VIEW analytics.dim_sales_rep AS

WITH rep_territory AS (
    SELECT
        za.rep_id,
        MIN(za.coverage_type) AS coverage_type,
        COUNT(*) AS assigned_zip_count

    FROM core.zip_rep_assignment za

    GROUP BY
        za.rep_id
)

SELECT
    -- Existing columns: preserve order and data types
    rt.rep_id,
    rt.coverage_type,
    rt.assigned_zip_count,

    -- Fictional representative identity
    org.rep_name,
    org.rep_display,

    -- Management hierarchy
    org.manager_id,
    org.manager_name,
    org.manager_display,
    org.region_name

FROM rep_territory rt

LEFT JOIN analytics.dim_sales_organization org
    ON rt.rep_id = org.rep_id;


-- ============================================================
-- 5. VALIDATE REPORTING DIMENSIONS
-- ============================================================

DO $$
DECLARE
    v_customers BIGINT;
    v_ship_tos BIGINT;
    v_products BIGINT;
    v_reps BIGINT;

    v_categories BIGINT;
    v_families BIGINT;

    v_missing_reps BIGINT;
    v_missing_products BIGINT;
    v_missing_customers BIGINT;
    v_missing_facilities BIGINT;

    v_mixed_rep_types BIGINT;
    v_zip_assignments BIGINT;

    -- Organization validation
    v_missing_organization BIGINT;
    v_duplicate_rep_labels BIGINT;
    v_coverage_mismatch BIGINT;
    v_manager_count BIGINT;
    v_field_managers BIGINT;
    v_inside_managers BIGINT;
    v_field_reps BIGINT;
    v_inside_reps BIGINT;

BEGIN

    -- --------------------------------------------------------
    -- Validate master dimension counts
    -- --------------------------------------------------------

    SELECT COUNT(*)
    INTO v_customers
    FROM analytics.dim_customer;

    SELECT COUNT(*)
    INTO v_ship_tos
    FROM analytics.dim_ship_to;

    SELECT COUNT(*)
    INTO v_products
    FROM analytics.dim_product;

    SELECT COUNT(*)
    INTO v_reps
    FROM analytics.dim_sales_rep;

    SELECT COUNT(DISTINCT category_id)
    INTO v_categories
    FROM analytics.dim_product;

    SELECT COUNT(DISTINCT family_id)
    INTO v_families
    FROM analytics.dim_product;

    IF v_customers <> 3000 THEN
        RAISE EXCEPTION
            'Customer count mismatch: %',
            v_customers;
    END IF;

    IF v_ship_tos <> 5000 THEN
        RAISE EXCEPTION
            'Ship-to count mismatch: %',
            v_ship_tos;
    END IF;

    IF v_products <> 1200 THEN
        RAISE EXCEPTION
            'Product count mismatch: %',
            v_products;
    END IF;

    IF v_categories <> 4 THEN
        RAISE EXCEPTION
            'Product category count mismatch: %',
            v_categories;
    END IF;

    IF v_families <> 24 THEN
        RAISE EXCEPTION
            'Product family count mismatch: %',
            v_families;
    END IF;

    IF v_reps <> 84 THEN
        RAISE EXCEPTION
            'Sales representative count mismatch: %',
            v_reps;
    END IF;


    -- --------------------------------------------------------
    -- Validate representative territory consistency
    -- --------------------------------------------------------

    SELECT COUNT(*)
    INTO v_mixed_rep_types
    FROM (
        SELECT
            rep_id
        FROM core.zip_rep_assignment
        GROUP BY rep_id
        HAVING COUNT(DISTINCT coverage_type) > 1
    ) x;

    IF v_mixed_rep_types <> 0 THEN
        RAISE EXCEPTION
            '% representatives have mixed coverage types.',
            v_mixed_rep_types;
    END IF;

    SELECT COALESCE(SUM(assigned_zip_count), 0)
    INTO v_zip_assignments
    FROM analytics.dim_sales_rep;

    IF v_zip_assignments <> 33300 THEN
        RAISE EXCEPTION
            'Representative ZIP assignments do not reconcile.';
    END IF;


    -- --------------------------------------------------------
    -- Validate organization hierarchy
    -- --------------------------------------------------------

    -- Every rep must have a fictional name and manager.

    SELECT COUNT(*)
    INTO v_missing_organization
    FROM analytics.dim_sales_rep
    WHERE rep_name IS NULL
       OR rep_display IS NULL
       OR manager_id IS NULL
       OR manager_name IS NULL
       OR manager_display IS NULL
       OR region_name IS NULL;

    IF v_missing_organization <> 0 THEN
        RAISE EXCEPTION
            '% representatives lack organization attributes.',
            v_missing_organization;
    END IF;


    -- Representative display labels must be unique.

    SELECT COUNT(*)
    INTO v_duplicate_rep_labels
    FROM (
        SELECT
            rep_display
        FROM analytics.dim_sales_rep
        GROUP BY rep_display
        HAVING COUNT(*) > 1
    ) x;

    IF v_duplicate_rep_labels <> 0 THEN
        RAISE EXCEPTION
            '% duplicate representative display labels.',
            v_duplicate_rep_labels;
    END IF;


    -- Field reps must report to Field managers.
    -- Inside reps must report to Inside managers.

    SELECT COUNT(*)
    INTO v_coverage_mismatch
    FROM analytics.dim_sales_rep r
    JOIN core.sales_manager m
        ON r.manager_id = m.manager_id
    WHERE r.coverage_type <> m.coverage_type;

    IF v_coverage_mismatch <> 0 THEN
        RAISE EXCEPTION
            '% representatives have incorrect manager coverage.',
            v_coverage_mismatch;
    END IF;


    -- Validate all seven management groups.

    SELECT
        COUNT(DISTINCT manager_id),
        COUNT(DISTINCT manager_id)
            FILTER (WHERE coverage_type = 'Field'),
        COUNT(DISTINCT manager_id)
            FILTER (WHERE coverage_type = 'Inside'),
        COUNT(*) FILTER (WHERE coverage_type = 'Field'),
        COUNT(*) FILTER (WHERE coverage_type = 'Inside')
    INTO
        v_manager_count,
        v_field_managers,
        v_inside_managers,
        v_field_reps,
        v_inside_reps
    FROM analytics.dim_sales_rep;

    IF v_manager_count <> 7 THEN
        RAISE EXCEPTION
            'Expected 7 managers, found %.',
            v_manager_count;
    END IF;

    IF v_field_managers <> 6 THEN
        RAISE EXCEPTION
            'Expected 6 Field managers, found %.',
            v_field_managers;
    END IF;

    IF v_inside_managers <> 1 THEN
        RAISE EXCEPTION
            'Expected 1 Inside manager, found %.',
            v_inside_managers;
    END IF;

    IF v_field_reps <> 78 THEN
        RAISE EXCEPTION
            'Expected 78 Field reps, found %.',
            v_field_reps;
    END IF;

    IF v_inside_reps <> 6 THEN
        RAISE EXCEPTION
            'Expected 6 Inside reps, found %.',
            v_inside_reps;
    END IF;


    -- --------------------------------------------------------
    -- Validate dimension relationships to fact
    -- --------------------------------------------------------

    SELECT COUNT(*)
    INTO v_missing_customers
    FROM analytics.fact_sales_transactions f
    LEFT JOIN analytics.dim_customer c
        ON f.customer_id = c.customer_id
    WHERE c.customer_id IS NULL;

    SELECT COUNT(*)
    INTO v_missing_facilities
    FROM analytics.fact_sales_transactions f
    LEFT JOIN analytics.dim_ship_to st
        ON f.ship_to_id = st.ship_to_id
    WHERE st.ship_to_id IS NULL;

    SELECT COUNT(*)
    INTO v_missing_products
    FROM analytics.fact_sales_transactions f
    LEFT JOIN analytics.dim_product p
        ON f.product_id = p.product_id
    WHERE p.product_id IS NULL;

    SELECT COUNT(*)
    INTO v_missing_reps
    FROM analytics.dim_ship_to st
    LEFT JOIN analytics.dim_sales_rep r
        ON st.assigned_rep_id = r.rep_id
    WHERE r.rep_id IS NULL;

    IF v_missing_customers <> 0 THEN
        RAISE EXCEPTION
            '% sales transactions lack a customer dimension.',
            v_missing_customers;
    END IF;

    IF v_missing_facilities <> 0 THEN
        RAISE EXCEPTION
            '% sales transactions lack a ship-to dimension.',
            v_missing_facilities;
    END IF;

    IF v_missing_products <> 0 THEN
        RAISE EXCEPTION
            '% sales transactions lack a product dimension.',
            v_missing_products;
    END IF;

    IF v_missing_reps <> 0 THEN
        RAISE EXCEPTION
            '% ship-to facilities lack a sales representative.',
            v_missing_reps;
    END IF;


    -- --------------------------------------------------------
    -- Validation results
    -- --------------------------------------------------------

    RAISE NOTICE
        'PASS: 3000 parent customers validated.';

    RAISE NOTICE
        'PASS: 5000 ship-to facilities validated.';

    RAISE NOTICE
        'PASS: 1200 products, 24 families, 4 categories validated.';

    RAISE NOTICE
        'PASS: 84 representatives covering 33300 ZIP codes.';

    RAISE NOTICE
        'PASS: 6 Field managers and 1 Inside manager.';

    RAISE NOTICE
        'PASS: 78 Field reps and 6 Inside reps.';

    RAISE NOTICE
        'PASS: Fictional names and reporting hierarchy validated.';

    RAISE NOTICE
        'PASS: All fact-to-dimension relationships validated.';

END $$;

COMMIT;


-- ============================================================
-- 6. DIMENSION SUMMARY
-- ============================================================

SELECT
    'Customers' AS dimension,
    COUNT(*) AS record_count
FROM analytics.dim_customer

UNION ALL

SELECT
    'Ship-to Facilities',
    COUNT(*)
FROM analytics.dim_ship_to

UNION ALL

SELECT
    'Products',
    COUNT(*)
FROM analytics.dim_product

UNION ALL

SELECT
    'Sales Representatives',
    COUNT(*)
FROM analytics.dim_sales_rep

ORDER BY dimension;


-- ============================================================
-- 7. SALES MANAGEMENT HIERARCHY SUMMARY
-- ============================================================

SELECT
    manager_id,
    manager_name,
    region_name,
    coverage_type,
    COUNT(*) AS rep_count,
    SUM(assigned_zip_count) AS assigned_zip_count

FROM analytics.dim_sales_rep

GROUP BY
    manager_id,
    manager_name,
    region_name,
    coverage_type

ORDER BY manager_id;