
-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- Monthly Sales Performance and KPI Views
--
-- Source:
--   analytics.fact_sales_transactions
--
-- Creates:
--   analytics.vw_monthly_sales_performance
--   analytics.vw_sales_kpi_summary
--
-- Metrics:
--   Monthly sales
--   Prior-year same-month sales
--   Monthly dollar and percentage variance
--   Current-year-to-date sales
--   Prior-year-to-date sales
--   YTD dollar and percentage variance
--
-- No source transactions are modified.
-- Safe to rerun.
-- ============================================================

BEGIN;


-- ============================================================
-- 1. MONTHLY SALES PERFORMANCE
-- ============================================================

CREATE OR REPLACE VIEW
    analytics.vw_monthly_sales_performance
AS

WITH monthly_sales AS (

    -- Aggregate signed shipment and return revenue
    -- by actual posting month.

    SELECT
        DATE_TRUNC(
            'month',
            posting_date
        )::DATE AS month_start_date,

        EXTRACT(
            YEAR FROM posting_date
        )::INTEGER AS calendar_year,

        EXTRACT(
            MONTH FROM posting_date
        )::INTEGER AS calendar_month,

        COUNT(*) AS transaction_count,

        COUNT(*) FILTER (
            WHERE transaction_type = 'SHIPMENT'
        ) AS shipment_count,

        COUNT(*) FILTER (
            WHERE transaction_type = 'RETURN'
        ) AS return_count,

        COALESCE(
            SUM(net_sales_amount),
            0
        )::NUMERIC(18,2) AS monthly_net_sales

    FROM analytics.fact_sales_transactions

    GROUP BY
        DATE_TRUNC('month', posting_date),
        EXTRACT(YEAR FROM posting_date),
        EXTRACT(MONTH FROM posting_date)

),

year_to_date AS (

    -- Running revenue total resets every calendar year.

    SELECT
        m.*,

        SUM(monthly_net_sales) OVER (
            PARTITION BY calendar_year
            ORDER BY calendar_month
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        )::NUMERIC(18,2) AS ytd_net_sales

    FROM monthly_sales m

),

year_comparison AS (

    SELECT
        cy.month_start_date,
        cy.calendar_year,
        cy.calendar_month,

        TO_CHAR(
            cy.month_start_date,
            'YYYY-MM'
        ) AS year_month,

        cy.transaction_count,
        cy.shipment_count,
        cy.return_count,

        cy.monthly_net_sales,

        py.monthly_net_sales
            AS prior_year_month_sales,

        cy.ytd_net_sales,

        py.ytd_net_sales
            AS prior_year_ytd_sales

    FROM year_to_date cy

    LEFT JOIN year_to_date py
        ON py.calendar_year = cy.calendar_year - 1
       AND py.calendar_month = cy.calendar_month

)

SELECT
    month_start_date,
    calendar_year,
    calendar_month,
    year_month,

    transaction_count,
    shipment_count,
    return_count,

    monthly_net_sales,
    prior_year_month_sales,

    CASE
        WHEN prior_year_month_sales IS NULL
        THEN NULL
        ELSE (
            monthly_net_sales
            - prior_year_month_sales
        )::NUMERIC(18,2)
    END AS monthly_dollar_variance,

    CASE
        WHEN prior_year_month_sales IS NULL
          OR prior_year_month_sales = 0
        THEN NULL
        ELSE ROUND(
            (
                monthly_net_sales
                - prior_year_month_sales
            ) * 100.0
            / ABS(prior_year_month_sales),
            2
        )
    END AS monthly_growth_pct,

    ytd_net_sales,
    prior_year_ytd_sales,

    CASE
        WHEN prior_year_ytd_sales IS NULL
        THEN NULL
        ELSE (
            ytd_net_sales
            - prior_year_ytd_sales
        )::NUMERIC(18,2)
    END AS ytd_dollar_variance,

    CASE
        WHEN prior_year_ytd_sales IS NULL
          OR prior_year_ytd_sales = 0
        THEN NULL
        ELSE ROUND(
            (
                ytd_net_sales
                - prior_year_ytd_sales
            ) * 100.0
            / ABS(prior_year_ytd_sales),
            2
        )
    END AS ytd_growth_pct

FROM year_comparison;


-- ============================================================
-- 2. LATEST REPORTING PERIOD KPI SUMMARY
--
-- Uses the latest month represented in the fact data.
-- It does not depend on the computer's current date.
--
-- This synthetic dataset is complete through Sep 2026.
-- Future loads should contain complete months before
-- allowing the reporting period to advance.
-- ============================================================

CREATE OR REPLACE VIEW
    analytics.vw_sales_kpi_summary
AS

WITH latest_month AS (

    SELECT
        MAX(month_start_date)
            AS reporting_month

    FROM analytics.vw_monthly_sales_performance

)

SELECT
    m.month_start_date AS reporting_month,

    m.year_month,

    m.calendar_year,
    m.calendar_month,

    m.monthly_net_sales
        AS current_month_sales,

    m.prior_year_month_sales,

    m.monthly_dollar_variance,
    m.monthly_growth_pct,

    m.ytd_net_sales
        AS current_ytd_sales,

    m.prior_year_ytd_sales,

    m.ytd_dollar_variance,
    m.ytd_growth_pct,

    m.transaction_count,
    m.shipment_count,
    m.return_count

FROM analytics.vw_monthly_sales_performance m

JOIN latest_month l
    ON m.month_start_date = l.reporting_month;


-- ============================================================
-- 3. VALIDATE REPORTING OUTPUT
-- ============================================================

DO $$
DECLARE
    v_month_count BIGINT;

    v_reporting_month DATE;

    v_current_ytd NUMERIC(18,2);
    v_current_month NUMERIC(18,2);

    v_prior_ytd NUMERIC(18,2);

    v_missing_prior_year BIGINT;

    v_2025_total NUMERIC(18,2);
    v_2026_total NUMERIC(18,2);

BEGIN

    -- We have 12 months for 2025
    -- and 9 months for 2026.

    SELECT COUNT(*)
    INTO v_month_count
    FROM analytics.vw_monthly_sales_performance;

    IF v_month_count <> 21 THEN
        RAISE EXCEPTION
            'Expected 21 reporting months, found %.',
            v_month_count;
    END IF;


    -- Reconcile annual totals.

    SELECT
        COALESCE(SUM(monthly_net_sales), 0)
    INTO v_2025_total
    FROM analytics.vw_monthly_sales_performance
    WHERE calendar_year = 2025;

    SELECT
        COALESCE(SUM(monthly_net_sales), 0)
    INTO v_2026_total
    FROM analytics.vw_monthly_sales_performance
    WHERE calendar_year = 2026;

    IF v_2025_total <> 500092428.09 THEN
        RAISE EXCEPTION
            '2025 revenue reconciliation failed: %.',
            v_2025_total;
    END IF;

    IF v_2026_total <> 392981461.96 THEN
        RAISE EXCEPTION
            '2026 revenue reconciliation failed: %.',
            v_2026_total;
    END IF;


    -- Ensure 2026 months have corresponding 2025 data.

    SELECT COUNT(*)
    INTO v_missing_prior_year
    FROM analytics.vw_monthly_sales_performance
    WHERE calendar_year = 2026
      AND prior_year_month_sales IS NULL;

    IF v_missing_prior_year <> 0 THEN
        RAISE EXCEPTION
            '% 2026 months lack prior-year comparisons.',
            v_missing_prior_year;
    END IF;


    -- Confirm latest reporting period.

    SELECT
        reporting_month,
        current_month_sales,
        current_ytd_sales,
        prior_year_ytd_sales

    INTO
        v_reporting_month,
        v_current_month,
        v_current_ytd,
        v_prior_ytd

    FROM analytics.vw_sales_kpi_summary;

    IF v_reporting_month <> DATE '2026-09-01' THEN
        RAISE EXCEPTION
            'Unexpected latest reporting month: %.',
            v_reporting_month;
    END IF;

    IF v_current_month <> 49232462.62 THEN
        RAISE EXCEPTION
            'September 2026 revenue does not reconcile.';
    END IF;

    IF v_current_ytd <> 392981461.96 THEN
        RAISE EXCEPTION
            '2026 YTD revenue does not reconcile.';
    END IF;

    IF v_prior_ytd IS NULL THEN
        RAISE EXCEPTION
            'Prior-year YTD revenue is missing.';
    END IF;


    RAISE NOTICE
        'PASS: 21 reporting months validated.';

    RAISE NOTICE
        'PASS: 2025 net sales $%.',
        v_2025_total;

    RAISE NOTICE
        'PASS: 2026 YTD net sales $%.',
        v_2026_total;

    RAISE NOTICE
        'PASS: Latest reporting month is September 2026.';

    RAISE NOTICE
        'PASS: Prior-year comparisons available.';

END $$;

COMMIT;


-- ============================================================
-- 4. SHOW CURRENT KPI RESULTS
-- ============================================================

SELECT
    reporting_month,
    current_month_sales,
    prior_year_month_sales,
    monthly_dollar_variance,
    monthly_growth_pct,
    current_ytd_sales,
    prior_year_ytd_sales,
    ytd_dollar_variance,
    ytd_growth_pct

FROM analytics.vw_sales_kpi_summary;
