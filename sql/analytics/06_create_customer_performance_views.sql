
-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- Customer Performance Reporting
--
-- Creates:
--   analytics.vw_customer_performance
--   analytics.vw_ship_to_performance
--
-- Features:
--   Current YTD vs prior-year comparable YTD
--   Current month vs prior-year same month
--   Dollar and percentage variance
--   Customer growth/decline classification
--   Decline priority ranking by dollars lost
--
-- Uses the latest month present in transaction data.
-- Does not modify core data.
-- Safe to rerun.
-- ============================================================

BEGIN;


-- ============================================================
-- 1. PARENT CUSTOMER PERFORMANCE
-- ============================================================

CREATE OR REPLACE VIEW analytics.vw_customer_performance AS

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

customer_sales AS (
    SELECT
        c.customer_id,
        c.customer_name,
        c.industry,
        c.customer_segment,

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

    FROM analytics.dim_customer c

    CROSS JOIN periods p

    LEFT JOIN analytics.fact_sales_transactions f
        ON f.customer_id = c.customer_id
       AND f.posting_date >= p.prior_year_start
       AND f.posting_date < p.current_month_end

    GROUP BY
        c.customer_id,
        c.customer_name,
        c.industry,
        c.customer_segment,
        p.current_month
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
                (current_month_sales - prior_year_month_sales)
                * 100.0 / ABS(prior_year_month_sales),
                2
            )
        END AS monthly_growth_pct

    FROM customer_sales
)

SELECT
    customer_id,
    customer_name,
    industry,
    customer_segment,
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
-- 2. SHIP-TO FACILITY PERFORMANCE
-- ============================================================

CREATE OR REPLACE VIEW analytics.vw_ship_to_performance AS

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

facility_sales AS (
    SELECT
        st.ship_to_id,
        st.customer_id,
        c.customer_name,

        st.ship_to_name,
        st.zip_code,

        st.assigned_rep_id,
        st.coverage_type,

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

    FROM analytics.dim_ship_to st

    JOIN analytics.dim_customer c
        ON st.customer_id = c.customer_id

    CROSS JOIN periods p

    LEFT JOIN analytics.fact_sales_transactions f
        ON f.ship_to_id = st.ship_to_id
       AND f.posting_date >= p.prior_year_start
       AND f.posting_date < p.current_month_end

    GROUP BY
        st.ship_to_id,
        st.customer_id,
        c.customer_name,
        st.ship_to_name,
        st.zip_code,
        st.assigned_rep_id,
        st.coverage_type,
        p.current_month
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
                (current_month_sales - prior_year_month_sales)
                * 100.0 / ABS(prior_year_month_sales),
                2
            )
        END AS monthly_growth_pct

    FROM facility_sales
)

SELECT
    ship_to_id,
    customer_id,
    customer_name,
    ship_to_name,
    zip_code,
    assigned_rep_id,
    coverage_type,
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
-- 3. VALIDATE CUSTOMER AND FACILITY RECONCILIATION
-- ============================================================

DO $$
DECLARE
    v_customer_count BIGINT;
    v_facility_count BIGINT;

    v_customer_cytd NUMERIC(18,2);
    v_customer_pytd NUMERIC(18,2);

    v_facility_cytd NUMERIC(18,2);
    v_facility_pytd NUMERIC(18,2);

    v_reporting_month DATE;

BEGIN

    SELECT
        COUNT(*),
        SUM(cytd_sales),
        SUM(pytd_sales),
        MIN(reporting_month)
    INTO
        v_customer_count,
        v_customer_cytd,
        v_customer_pytd,
        v_reporting_month
    FROM analytics.vw_customer_performance;

    IF v_customer_count <> 3000 THEN
        RAISE EXCEPTION
            'Expected 3000 parent customers; found %.',
            v_customer_count;
    END IF;

    IF v_reporting_month <> DATE '2026-09-01' THEN
        RAISE EXCEPTION
            'Unexpected reporting month: %.',
            v_reporting_month;
    END IF;

    SELECT
        COUNT(*),
        SUM(cytd_sales),
        SUM(pytd_sales)
    INTO
        v_facility_count,
        v_facility_cytd,
        v_facility_pytd
    FROM analytics.vw_ship_to_performance;

    IF v_facility_count <> 5000 THEN
        RAISE EXCEPTION
            'Expected 5000 facilities; found %.',
            v_facility_count;
    END IF;

    IF v_customer_cytd <> 392981461.96
       OR v_facility_cytd <> 392981461.96
    THEN
        RAISE EXCEPTION
            '2026 YTD customer/facility revenue mismatch.';
    END IF;

    IF v_customer_pytd <> 373710981.60
       OR v_facility_pytd <> 373710981.60
    THEN
        RAISE EXCEPTION
            '2025 comparable YTD revenue mismatch.';
    END IF;

    RAISE NOTICE
        'PASS: 3000 parent customers validated.';

    RAISE NOTICE
        'PASS: 5000 ship-to facilities validated.';

    RAISE NOTICE
        'PASS: CYTD customer and facility totals reconcile.';

    RAISE NOTICE
        'PASS: PYTD customer and facility totals reconcile.';

END $$;

COMMIT;


-- ============================================================
-- 4. SHOW THE TOP 20 DECLINING PARENT CUSTOMERS
-- ============================================================

SELECT
    customer_id,
    customer_name,
    industry,
    cytd_sales,
    pytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct,
    performance_status,
    decline_priority_rank

FROM analytics.vw_customer_performance

WHERE ytd_dollar_variance < 0

ORDER BY
    ytd_dollar_variance ASC,
    customer_id

LIMIT 20;
