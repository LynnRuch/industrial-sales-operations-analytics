
-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- Product Performance Reporting
--
-- Product hierarchy:
--   Category -> Family -> SKU
--
-- Creates:
--   analytics.vw_product_performance
--   analytics.vw_product_family_performance
--   analytics.vw_product_category_performance
--
-- Metrics:
--   Current month and prior-year same month
--   CYTD and comparable PYTD
--   Dollar and percentage variances
--   Growth/decline classification
--   Decline rankings by dollars lost
--
-- Reporting month is derived from loaded transactions.
-- No source data is changed.
-- Safe to rerun.
-- ============================================================

BEGIN;


-- ============================================================
-- 1. SKU-LEVEL PRODUCT PERFORMANCE
-- ============================================================

CREATE OR REPLACE VIEW analytics.vw_product_performance AS

WITH reporting_period AS (
    SELECT
        DATE_TRUNC(
            'month',
            MAX(posting_date)
        )::DATE AS current_month
    FROM analytics.fact_sales_transactions
),

periods AS (
    SELECT
        current_month,

        DATE_TRUNC(
            'year',
            current_month
        )::DATE AS current_year_start,

        (
            current_month - INTERVAL '1 year'
        )::DATE AS prior_month,

        (
            DATE_TRUNC('year', current_month)
            - INTERVAL '1 year'
        )::DATE AS prior_year_start,

        (
            current_month + INTERVAL '1 month'
        )::DATE AS current_month_end,

        (
            current_month - INTERVAL '11 months'
        )::DATE AS prior_month_end

    FROM reporting_period
),

product_sales AS (
    SELECT
        p.product_id,
        p.sku,
        p.product_name,
        p.unit_of_measure,
        p.active_flag,

        p.family_id,
        p.family_name,

        p.category_id,
        p.category_name,

        rp.current_month AS reporting_month,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= rp.current_year_start
                  AND f.posting_date < rp.current_month_end
            ),
            0
        )::NUMERIC(18,2) AS cytd_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= rp.prior_year_start
                  AND f.posting_date < rp.prior_month_end
            ),
            0
        )::NUMERIC(18,2) AS pytd_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= rp.current_month
                  AND f.posting_date < rp.current_month_end
            ),
            0
        )::NUMERIC(18,2) AS current_month_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= rp.prior_month
                  AND f.posting_date < rp.prior_month_end
            ),
            0
        )::NUMERIC(18,2) AS prior_year_month_sales

    FROM analytics.dim_product p

    CROSS JOIN periods rp

    LEFT JOIN analytics.fact_sales_transactions f
        ON f.product_id = p.product_id
       AND f.posting_date >= rp.prior_year_start
       AND f.posting_date < rp.current_month_end

    GROUP BY
        p.product_id,
        p.sku,
        p.product_name,
        p.unit_of_measure,
        p.active_flag,
        p.family_id,
        p.family_name,
        p.category_id,
        p.category_name,
        rp.current_month
),

calculated AS (
    SELECT
        *,

        (
            cytd_sales - pytd_sales
        )::NUMERIC(18,2) AS ytd_dollar_variance,

        CASE
            WHEN pytd_sales = 0 THEN NULL
            ELSE ROUND(
                (cytd_sales - pytd_sales)
                * 100.0 / ABS(pytd_sales),
                2
            )
        END AS ytd_growth_pct,

        (
            current_month_sales - prior_year_month_sales
        )::NUMERIC(18,2) AS monthly_dollar_variance,

        CASE
            WHEN prior_year_month_sales = 0 THEN NULL
            ELSE ROUND(
                (
                    current_month_sales
                    - prior_year_month_sales
                ) * 100.0 / ABS(prior_year_month_sales),
                2
            )
        END AS monthly_growth_pct

    FROM product_sales
)

SELECT
    product_id,
    sku,
    product_name,
    unit_of_measure,
    active_flag,

    family_id,
    family_name,
    category_id,
    category_name,

    reporting_month,

    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,

    current_month_sales,
    prior_year_month_sales,
    monthly_dollar_variance,
    monthly_growth_pct,

    CASE
        WHEN cytd_sales = 0 AND pytd_sales = 0
            THEN 'No Sales'
        WHEN pytd_sales = 0 AND cytd_sales > 0
            THEN 'New'
        WHEN pytd_sales > 0 AND cytd_sales = 0
            THEN 'Lost'
        WHEN ytd_dollar_variance < 0
            THEN 'Declining'
        WHEN ytd_dollar_variance > 0
            THEN 'Growing'
        ELSE 'Flat'
    END AS performance_status,

    CASE
        WHEN ytd_dollar_variance < 0 THEN
            DENSE_RANK() OVER (
                PARTITION BY (ytd_dollar_variance < 0)
                ORDER BY ytd_dollar_variance ASC
            )
        ELSE NULL
    END AS decline_priority_rank

FROM calculated;


-- ============================================================
-- 2. PRODUCT FAMILY PERFORMANCE
--
-- Roll up SKU revenue to the family level.
-- ============================================================

CREATE OR REPLACE VIEW
    analytics.vw_product_family_performance
AS

WITH family_sales AS (
    SELECT
        family_id,
        family_name,
        category_id,
        category_name,
        reporting_month,

        COUNT(*) AS sku_count,

        SUM(cytd_sales)::NUMERIC(18,2)
            AS cytd_sales,

        SUM(pytd_sales)::NUMERIC(18,2)
            AS pytd_sales,

        SUM(current_month_sales)::NUMERIC(18,2)
            AS current_month_sales,

        SUM(prior_year_month_sales)::NUMERIC(18,2)
            AS prior_year_month_sales

    FROM analytics.vw_product_performance

    GROUP BY
        family_id,
        family_name,
        category_id,
        category_name,
        reporting_month
),

calculated AS (
    SELECT
        *,

        (cytd_sales - pytd_sales)::NUMERIC(18,2)
            AS ytd_dollar_variance,

        CASE
            WHEN pytd_sales = 0 THEN NULL
            ELSE ROUND(
                (cytd_sales - pytd_sales)
                * 100.0 / ABS(pytd_sales),
                2
            )
        END AS ytd_growth_pct,

        (
            current_month_sales - prior_year_month_sales
        )::NUMERIC(18,2) AS monthly_dollar_variance,

        CASE
            WHEN prior_year_month_sales = 0 THEN NULL
            ELSE ROUND(
                (
                    current_month_sales
                    - prior_year_month_sales
                ) * 100.0 / ABS(prior_year_month_sales),
                2
            )
        END AS monthly_growth_pct

    FROM family_sales
)

SELECT
    family_id,
    family_name,
    category_id,
    category_name,
    reporting_month,
    sku_count,

    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,

    current_month_sales,
    prior_year_month_sales,
    monthly_dollar_variance,
    monthly_growth_pct,

    CASE
        WHEN cytd_sales = 0 AND pytd_sales = 0
            THEN 'No Sales'
        WHEN pytd_sales = 0 AND cytd_sales > 0
            THEN 'New'
        WHEN pytd_sales > 0 AND cytd_sales = 0
            THEN 'Lost'
        WHEN ytd_dollar_variance < 0
            THEN 'Declining'
        WHEN ytd_dollar_variance > 0
            THEN 'Growing'
        ELSE 'Flat'
    END AS performance_status,

    CASE
        WHEN ytd_dollar_variance < 0 THEN
            DENSE_RANK() OVER (
                PARTITION BY (ytd_dollar_variance < 0)
                ORDER BY ytd_dollar_variance ASC
            )
        ELSE NULL
    END AS decline_priority_rank

FROM calculated;


-- ============================================================
-- 3. PRODUCT CATEGORY PERFORMANCE
--
-- Roll up the family-level results to categories.
-- ============================================================

CREATE OR REPLACE VIEW
    analytics.vw_product_category_performance
AS

WITH category_sales AS (
    SELECT
        category_id,
        category_name,
        reporting_month,

        COUNT(*) AS family_count,
        SUM(sku_count) AS sku_count,

        SUM(cytd_sales)::NUMERIC(18,2)
            AS cytd_sales,

        SUM(pytd_sales)::NUMERIC(18,2)
            AS pytd_sales,

        SUM(current_month_sales)::NUMERIC(18,2)
            AS current_month_sales,

        SUM(prior_year_month_sales)::NUMERIC(18,2)
            AS prior_year_month_sales

    FROM analytics.vw_product_family_performance

    GROUP BY
        category_id,
        category_name,
        reporting_month
),

calculated AS (
    SELECT
        *,

        (cytd_sales - pytd_sales)::NUMERIC(18,2)
            AS ytd_dollar_variance,

        CASE
            WHEN pytd_sales = 0 THEN NULL
            ELSE ROUND(
                (cytd_sales - pytd_sales)
                * 100.0 / ABS(pytd_sales),
                2
            )
        END AS ytd_growth_pct,

        (
            current_month_sales - prior_year_month_sales
        )::NUMERIC(18,2) AS monthly_dollar_variance,

        CASE
            WHEN prior_year_month_sales = 0 THEN NULL
            ELSE ROUND(
                (
                    current_month_sales
                    - prior_year_month_sales
                ) * 100.0 / ABS(prior_year_month_sales),
                2
            )
        END AS monthly_growth_pct

    FROM category_sales
)

SELECT
    category_id,
    category_name,
    reporting_month,

    family_count,
    sku_count,

    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,

    current_month_sales,
    prior_year_month_sales,
    monthly_dollar_variance,
    monthly_growth_pct,

    CASE
        WHEN cytd_sales = 0 AND pytd_sales = 0
            THEN 'No Sales'
        WHEN pytd_sales = 0 AND cytd_sales > 0
            THEN 'New'
        WHEN pytd_sales > 0 AND cytd_sales = 0
            THEN 'Lost'
        WHEN ytd_dollar_variance < 0
            THEN 'Declining'
        WHEN ytd_dollar_variance > 0
            THEN 'Growing'
        ELSE 'Flat'
    END AS performance_status,

    CASE
        WHEN ytd_dollar_variance < 0 THEN
            DENSE_RANK() OVER (
                PARTITION BY (ytd_dollar_variance < 0)
                ORDER BY ytd_dollar_variance ASC
            )
        ELSE NULL
    END AS decline_priority_rank

FROM calculated;


-- ============================================================
-- 4. VALIDATE THE PRODUCT HIERARCHY AND SALES TOTALS
-- ============================================================

DO $$
DECLARE
    v_sku_count BIGINT;
    v_family_count BIGINT;
    v_category_count BIGINT;

    v_sku_cytd NUMERIC(18,2);
    v_family_cytd NUMERIC(18,2);
    v_category_cytd NUMERIC(18,2);

    v_sku_pytd NUMERIC(18,2);
    v_family_pytd NUMERIC(18,2);
    v_category_pytd NUMERIC(18,2);

    v_sku_month NUMERIC(18,2);
    v_family_month NUMERIC(18,2);
    v_category_month NUMERIC(18,2);

    v_sku_prior_month NUMERIC(18,2);
    v_family_prior_month NUMERIC(18,2);
    v_category_prior_month NUMERIC(18,2);

    v_reporting_month DATE;

BEGIN

    SELECT
        COUNT(*),
        SUM(cytd_sales),
        SUM(pytd_sales),
        SUM(current_month_sales),
        SUM(prior_year_month_sales),
        MIN(reporting_month)
    INTO
        v_sku_count,
        v_sku_cytd,
        v_sku_pytd,
        v_sku_month,
        v_sku_prior_month,
        v_reporting_month
    FROM analytics.vw_product_performance;

    SELECT
        COUNT(*),
        SUM(cytd_sales),
        SUM(pytd_sales),
        SUM(current_month_sales),
        SUM(prior_year_month_sales)
    INTO
        v_family_count,
        v_family_cytd,
        v_family_pytd,
        v_family_month,
        v_family_prior_month
    FROM analytics.vw_product_family_performance;

    SELECT
        COUNT(*),
        SUM(cytd_sales),
        SUM(pytd_sales),
        SUM(current_month_sales),
        SUM(prior_year_month_sales)
    INTO
        v_category_count,
        v_category_cytd,
        v_category_pytd,
        v_category_month,
        v_category_prior_month
    FROM analytics.vw_product_category_performance;

    -- Dimension counts

    IF v_sku_count <> 1200 THEN
        RAISE EXCEPTION
            'Expected 1200 SKUs; found %.',
            v_sku_count;
    END IF;

    IF v_family_count <> 24 THEN
        RAISE EXCEPTION
            'Expected 24 families; found %.',
            v_family_count;
    END IF;

    IF v_category_count <> 4 THEN
        RAISE EXCEPTION
            'Expected 4 categories; found %.',
            v_category_count;
    END IF;

    -- Reporting cutoff

    IF v_reporting_month <> DATE '2026-09-01' THEN
        RAISE EXCEPTION
            'Unexpected reporting month: %.',
            v_reporting_month;
    END IF;

    -- CYTD reconciliation

    IF v_sku_cytd <> 392981461.96
       OR v_family_cytd <> 392981461.96
       OR v_category_cytd <> 392981461.96
    THEN
        RAISE EXCEPTION
            'Product CYTD revenue reconciliation failed.';
    END IF;

    -- PYTD reconciliation

    IF v_sku_pytd <> 373710981.60
       OR v_family_pytd <> 373710981.60
       OR v_category_pytd <> 373710981.60
    THEN
        RAISE EXCEPTION
            'Product PYTD revenue reconciliation failed.';
    END IF;

    -- Current-month reconciliation

    IF v_sku_month <> 49232462.62
       OR v_family_month <> 49232462.62
       OR v_category_month <> 49232462.62
    THEN
        RAISE EXCEPTION
            'Product current-month revenue reconciliation failed.';
    END IF;

    -- Prior-year same-month reconciliation

    IF v_sku_prior_month <> 46717461.10
       OR v_family_prior_month <> 46717461.10
       OR v_category_prior_month <> 46717461.10
    THEN
        RAISE EXCEPTION
            'Product prior-year month reconciliation failed.';
    END IF;

    RAISE NOTICE
        'PASS: 1200 SKUs validated.';

    RAISE NOTICE
        'PASS: 24 product families validated.';

    RAISE NOTICE
        'PASS: 4 product categories validated.';

    RAISE NOTICE
        'PASS: CYTD, PYTD, and monthly revenue reconcile at all hierarchy levels.';

END $$;

COMMIT;


-- ============================================================
-- 5. DISPLAY CATEGORY PERFORMANCE
-- ============================================================

SELECT
    category_name,
    family_count,
    sku_count,
    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,
    performance_status
FROM analytics.vw_product_category_performance
ORDER BY cytd_sales DESC;
