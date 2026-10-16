
-- ============================================================
-- Industrial Sales Operations Analytics
-- Analytics Date Dimension
--
-- Calendar coverage: January 2025–December 2026
-- Reporting data currently ends September 2026.
--
-- Safe to rerun.
-- Does not modify core transaction data.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_key INTEGER PRIMARY KEY,
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    month_name VARCHAR(15) NOT NULL,
    month_short_name VARCHAR(3) NOT NULL,
    year_month VARCHAR(7) NOT NULL,
    month_start_date DATE NOT NULL,
    month_end_date DATE NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name VARCHAR(10) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

INSERT INTO analytics.dim_date (
    date_key,
    calendar_date,
    calendar_year,
    calendar_quarter,
    calendar_month,
    month_name,
    month_short_name,
    year_month,
    month_start_date,
    month_end_date,
    day_of_month,
    day_of_week,
    day_name,
    is_weekend
)
SELECT
    TO_CHAR(d.calendar_date, 'YYYYMMDD')::INTEGER,
    d.calendar_date,
    EXTRACT(YEAR FROM d.calendar_date)::INTEGER,
    EXTRACT(QUARTER FROM d.calendar_date)::INTEGER,
    EXTRACT(MONTH FROM d.calendar_date)::INTEGER,
    TO_CHAR(d.calendar_date, 'FMMonth'),
    TO_CHAR(d.calendar_date, 'Mon'),
    TO_CHAR(d.calendar_date, 'YYYY-MM'),
    DATE_TRUNC('month', d.calendar_date)::DATE,
    (
        DATE_TRUNC('month', d.calendar_date)
        + INTERVAL '1 month - 1 day'
    )::DATE,
    EXTRACT(DAY FROM d.calendar_date)::INTEGER,
    EXTRACT(ISODOW FROM d.calendar_date)::INTEGER,
    TO_CHAR(d.calendar_date, 'FMDay'),
    EXTRACT(ISODOW FROM d.calendar_date) IN (6, 7)
FROM GENERATE_SERIES(
    DATE '2025-01-01',
    DATE '2026-12-31',
    INTERVAL '1 day'
) AS d(calendar_date)
ON CONFLICT (date_key) DO NOTHING;

-- Validate complete calendar coverage.

DO $$
DECLARE
    v_date_count INTEGER;
    v_missing_transactions BIGINT;
BEGIN

    SELECT COUNT(*)
    INTO v_date_count
    FROM analytics.dim_date
    WHERE calendar_date BETWEEN
        DATE '2025-01-01'
        AND DATE '2026-12-31';

    IF v_date_count <> 730 THEN
        RAISE EXCEPTION
            'Date dimension incomplete: % days found.',
            v_date_count;
    END IF;

    SELECT COUNT(*)
    INTO v_missing_transactions
    FROM core.sales_transaction s
    LEFT JOIN analytics.dim_date d
      ON s.posting_date = d.calendar_date
    WHERE d.date_key IS NULL;

    IF v_missing_transactions <> 0 THEN
        RAISE EXCEPTION
            '% transactions have no matching calendar date.',
            v_missing_transactions;
    END IF;

    RAISE NOTICE
        'PASS: Date dimension contains 730 calendar days.';

    RAISE NOTICE
        'PASS: All core transactions match a calendar date.';

END $$;

COMMIT;

-- Display calendar coverage.
SELECT
    COUNT(*) AS calendar_days,
    MIN(calendar_date) AS first_date,
    MAX(calendar_date) AS last_date
FROM analytics.dim_date;
