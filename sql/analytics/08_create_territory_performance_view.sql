
-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- Territory Sales Performance
--
-- Creates:
--   analytics.vw_territory_performance
--
-- Business rules:
--   - Ship-to ZIP determines sales credit
--   - One representative per ZIP
--   - Current ZIP ownership applies to both years
--   - Field and Inside territories reported separately
--   - Declines prioritized by dollar loss
--
-- Reporting period:
--   Latest month represented in loaded sales data
--
-- Read-only reporting view.
-- No source data or assignments are modified.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. TERRITORY PERFORMANCE VIEW
-- ============================================================

CREATE OR REPLACE VIEW
    analytics.vw_territory_performance
AS

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
            current_month - INTERVAL '1 year'
            + INTERVAL '1 month'
        )::DATE AS prior_month_end

    FROM reporting_period
),

territory_sales AS (
    SELECT
        r.rep_id,
        r.coverage_type,
        r.assigned_zip_count,

        p.current_month AS reporting_month,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= p.current_year_start
                  AND f.posting_date < p.current_month_end
            ),
            0
        )::NUMERIC(18,2) AS cytd_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= p.prior_year_start
                  AND f.posting_date < p.prior_month_end
            ),
            0
        )::NUMERIC(18,2) AS pytd_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= p.current_month
                  AND f.posting_date < p.current_month_end
            ),
            0
        )::NUMERIC(18,2) AS current_month_sales,

        COALESCE(
            SUM(f.net_sales_amount) FILTER (
                WHERE f.posting_date >= p.prior_month
                  AND f.posting_date < p.prior_month_end
            ),
            0
        )::NUMERIC(18,2) AS prior_year_month_sales

    FROM analytics.dim_sales_rep r

    CROSS JOIN periods p

    LEFT JOIN analytics.fact_sales_transactions f
        ON f.assigned_rep_id = r.rep_id
       AND f.posting_date >= p.prior_year_start
       AND f.posting_date < p.current_month_end

    GROUP BY
        r.rep_id,
        r.coverage_type,
        r.assigned_zip_count,
        p.current_month
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

    FROM territory_sales
)

SELECT
    rep_id,
    coverage_type,
    assigned_zip_count,
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
                PARTITION BY
                    (ytd_dollar_variance < 0)
                ORDER BY ytd_dollar_variance ASC
            )
        ELSE NULL
    END AS decline_priority_rank

FROM calculated;


-- ============================================================
-- 2. VALIDATE TERRITORY RECONCILIATION
-- ============================================================

DO $$
DECLARE
    v_rep_count BIGINT;
    v_field_reps BIGINT;
    v_inside_reps BIGINT;

    v_assigned_zips BIGINT;

    v_cytd NUMERIC(18,2);
    v_pytd NUMERIC(18,2);

    v_current_month NUMERIC(18,2);
    v_prior_month NUMERIC(18,2);

    v_reporting_month DATE;

    v_missing_reps BIGINT;
    v_invalid_coverage BIGINT;

BEGIN

    -- --------------------------------------------------------
    -- Validate representative counts and coverage
    -- --------------------------------------------------------

    SELECT
        COUNT(*),

        COUNT(*) FILTER (
            WHERE coverage_type = 'Field'
        ),

        COUNT(*) FILTER (
            WHERE coverage_type = 'Inside'
        ),

        COALESCE(
            SUM(assigned_zip_count),
            0
        ),

        MIN(reporting_month),

        COALESCE(SUM(cytd_sales), 0),
        COALESCE(SUM(pytd_sales), 0),

        COALESCE(SUM(current_month_sales), 0),
        COALESCE(SUM(prior_year_month_sales), 0)

    INTO
        v_rep_count,
        v_field_reps,
        v_inside_reps,
        v_assigned_zips,
        v_reporting_month,
        v_cytd,
        v_pytd,
        v_current_month,
        v_prior_month

    FROM analytics.vw_territory_performance;


    IF v_rep_count <> 84 THEN
        RAISE EXCEPTION
            'Expected 84 representatives; found %.',
            v_rep_count;
    END IF;

    IF v_field_reps <> 78 THEN
        RAISE EXCEPTION
            'Expected 78 Field reps; found %.',
            v_field_reps;
    END IF;

    IF v_inside_reps <> 6 THEN
        RAISE EXCEPTION
            'Expected 6 Inside reps; found %.',
            v_inside_reps;
    END IF;

    IF v_assigned_zips <> 33300 THEN
        RAISE EXCEPTION
            'Territory ZIP count mismatch: %.',
            v_assigned_zips;
    END IF;


    -- --------------------------------------------------------
    -- Validate latest completed reporting month
    -- --------------------------------------------------------

    IF v_reporting_month <> DATE '2026-09-01' THEN
        RAISE EXCEPTION
            'Unexpected reporting month: %.',
            v_reporting_month;
    END IF;


    -- --------------------------------------------------------
    -- CYTD and PYTD reconciliation
    -- --------------------------------------------------------

    IF v_cytd <> 392981461.96 THEN
        RAISE EXCEPTION
            'Territory CYTD mismatch: %.',
            v_cytd;
    END IF;

    IF v_pytd <> 373710981.60 THEN
        RAISE EXCEPTION
            'Territory PYTD mismatch: %.',
            v_pytd;
    END IF;


    -- --------------------------------------------------------
    -- Current month and prior-year month
    -- --------------------------------------------------------

    IF v_current_month <> 49232462.62 THEN
        RAISE EXCEPTION
            'Territory current-month mismatch: %.',
            v_current_month;
    END IF;

    IF v_prior_month <> 46717461.10 THEN
        RAISE EXCEPTION
            'Territory prior-year month mismatch: %.',
            v_prior_month;
    END IF;


    -- --------------------------------------------------------
    -- Ensure every transaction has a valid rep
    -- --------------------------------------------------------

    SELECT COUNT(*)
    INTO v_missing_reps
    FROM analytics.fact_sales_transactions f
    LEFT JOIN analytics.dim_sales_rep r
        ON f.assigned_rep_id = r.rep_id
    WHERE r.rep_id IS NULL;

    IF v_missing_reps <> 0 THEN
        RAISE EXCEPTION
            '% sales transactions have no valid rep.',
            v_missing_reps;
    END IF;


    -- --------------------------------------------------------
    -- Validate Field/Inside consistency
    -- --------------------------------------------------------

    SELECT COUNT(*)
    INTO v_invalid_coverage
    FROM analytics.fact_sales_transactions f
    JOIN analytics.dim_sales_rep r
        ON f.assigned_rep_id = r.rep_id
    WHERE f.coverage_type IS DISTINCT FROM r.coverage_type;

    IF v_invalid_coverage <> 0 THEN
        RAISE EXCEPTION
            '% transactions have inconsistent coverage.',
            v_invalid_coverage;
    END IF;


    RAISE NOTICE
        'PASS: 84 representatives validated.';

    RAISE NOTICE
        'PASS: 78 Field and 6 Inside reps validated.';

    RAISE NOTICE
        'PASS: 33300 ZIP assignments reconciled.';

    RAISE NOTICE
        'PASS: CYTD territory revenue $%.',
        v_cytd;

    RAISE NOTICE
        'PASS: PYTD territory revenue $%.',
        v_pytd;

    RAISE NOTICE
        'PASS: Current and prior-year monthly revenue reconciled.';

    RAISE NOTICE
        'PASS: All transaction territory relationships validated.';

END $$;

COMMIT;


-- ============================================================
-- 3. DISPLAY TERRITORY PERFORMANCE
--
-- Show the 20 representatives with the largest YTD
-- revenue declines, ranked by dollar impact.
-- ============================================================

SELECT
    rep_id,
    coverage_type,
    assigned_zip_count,
    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,
    performance_status,
    decline_priority_rank

FROM analytics.vw_territory_performance

WHERE ytd_dollar_variance < 0

ORDER BY
    ytd_dollar_variance ASC,
    rep_id

LIMIT 20;
