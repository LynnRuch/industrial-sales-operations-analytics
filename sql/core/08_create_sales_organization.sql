-- ============================================================
-- INDUSTRIAL SALES OPERATIONS ANALYTICS
-- SALES ORGANIZATION & MANAGEMENT HIERARCHY
--
-- 6 Field Sales Managers
-- 1 Inside Sales Manager
-- 78 Field Sales Representatives
-- 6 Inside Sales Representatives
--
-- Geographic assignments based on reviewed 2026 YTD data.
-- Existing territories and transactions are not modified.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. CREATE SALES MANAGER TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS core.sales_manager (
    manager_id VARCHAR(12) PRIMARY KEY,
    manager_name VARCHAR(100) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    coverage_type VARCHAR(10) NOT NULL
        CHECK (coverage_type IN ('Field', 'Inside'))
);

-- ============================================================
-- 2. CREATE SALES REP ORGANIZATION TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS core.sales_rep_organization (
    rep_id VARCHAR(20) PRIMARY KEY,
    rep_name VARCHAR(100) NOT NULL,
    manager_id VARCHAR(12) NOT NULL
        REFERENCES core.sales_manager(manager_id)
);

-- Protect existing mappings if this script was already run.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM core.sales_manager)
       OR EXISTS (SELECT 1 FROM core.sales_rep_organization)
    THEN
        RAISE EXCEPTION
            'Sales organization already contains data. No changes made.';
    END IF;
END $$;

-- ============================================================
-- 3. INSERT SEVEN FICTIONAL SALES MANAGERS
-- ============================================================

INSERT INTO core.sales_manager
    (manager_id, manager_name, region_name, coverage_type)
VALUES
    ('MGR-F01', 'Alexandra Mercer',
        'Pacific Northwest & West', 'Field'),

    ('MGR-F02', 'Daniel Navarro',
        'Southwest & Mountain', 'Field'),

    ('MGR-F03', 'Priya Collins',
        'Southeast', 'Field'),

    ('MGR-F04', 'Marcus Ellison',
        'Central & Plains', 'Field'),

    ('MGR-F05', 'Elena Brooks',
        'Great Lakes & Ohio Valley', 'Field'),

    ('MGR-F06', 'Christopher Hale',
        'Northeast & Mid-Atlantic', 'Field'),

    ('MGR-I01', 'Samantha Reed',
        'Inside Sales', 'Inside');

-- ============================================================
-- 4. INSERT 78 FIELD REPRESENTATIVES
--    Geographic management assignments are preserved.
-- ============================================================

INSERT INTO core.sales_rep_organization
    (rep_id, rep_name, manager_id)
VALUES
    ('FLD001', 'Avery Bennett', 'MGR-F03'),
    ('FLD002', 'Morgan Sullivan', 'MGR-F02'),
    ('FLD003', 'Jordan Reed', 'MGR-F03'),
    ('FLD004', 'Taylor Fletcher', 'MGR-F02'),
    ('FLD005', 'Parker Coleman', 'MGR-F02'),
    ('FLD006', 'Riley Ramirez', 'MGR-F03'),
    ('FLD007', 'Casey Holloway', 'MGR-F03'),
    ('FLD008', 'Cameron Patel', 'MGR-F03'),
    ('FLD009', 'Quinn Harrison', 'MGR-F03'),
    ('FLD010', 'Rowan Morgan', 'MGR-F02'),
    ('FLD011', 'Jamie Parker', 'MGR-F02'),
    ('FLD012', 'Skyler Whitaker', 'MGR-F02'),
    ('FLD013', 'Drew Daniels', 'MGR-F03'),
    ('FLD014', 'Reese Brooks', 'MGR-F03'),
    ('FLD015', 'Emerson Santos', 'MGR-F03'),
    ('FLD016', 'Hayden Keller', 'MGR-F03'),
    ('FLD017', 'Finley Walsh', 'MGR-F02'),
    ('FLD018', 'Sage Mitchell', 'MGR-F01'),
    ('FLD019', 'Elliot Hart', 'MGR-F03'),
    ('FLD020', 'Blair Jennings', 'MGR-F03'),
    ('FLD021', 'Harper Hayes', 'MGR-F01'),
    ('FLD022', 'Kendall Morales', 'MGR-F03'),
    ('FLD023', 'Logan Grant', 'MGR-F02'),
    ('FLD024', 'Sydney Ellis', 'MGR-F02'),
    ('FLD025', 'Alex Carter', 'MGR-F03'),
    ('FLD026', 'Charlie Hughes', 'MGR-F03'),
    ('FLD027', 'Dakota Dawson', 'MGR-F05'),
    ('FLD028', 'Jules Bishop', 'MGR-F03'),
    ('FLD029', 'Avery Foster', 'MGR-F04'),
    ('FLD030', 'Morgan Lawson', 'MGR-F06'),
    ('FLD031', 'Jordan Mills', 'MGR-F05'),
    ('FLD032', 'Taylor Porter', 'MGR-F04'),
    ('FLD033', 'Parker Baxter', 'MGR-F01'),
    ('FLD034', 'Riley Stone', 'MGR-F02'),
    ('FLD035', 'Casey Caldwell', 'MGR-F05'),
    ('FLD036', 'Cameron Hudson', 'MGR-F06'),
    ('FLD037', 'Quinn Perry', 'MGR-F05'),
    ('FLD038', 'Rowan Wells', 'MGR-F04'),
    ('FLD039', 'Jamie Fisher', 'MGR-F05'),
    ('FLD040', 'Skyler Nolan', 'MGR-F02'),
    ('FLD041', 'Drew Graham', 'MGR-F04'),
    ('FLD042', 'Reese Fields', 'MGR-F06'),
    ('FLD043', 'Emerson Conway', 'MGR-F04'),
    ('FLD044', 'Hayden Price', 'MGR-F01'),
    ('FLD045', 'Finley Hale', 'MGR-F02'),
    ('FLD046', 'Sage Campbell', 'MGR-F06'),
    ('FLD047', 'Elliot Bell', 'MGR-F04'),
    ('FLD048', 'Blair Mendoza', 'MGR-F06'),
    ('FLD049', 'Harper Palmer', 'MGR-F05'),
    ('FLD050', 'Kendall Floyd', 'MGR-F06'),
    ('FLD051', 'Logan Murray', 'MGR-F01'),
    ('FLD052', 'Sydney Ortiz', 'MGR-F05'),
    ('FLD053', 'Alex Steele', 'MGR-F05'),
    ('FLD054', 'Charlie Collins', 'MGR-F05'),
    ('FLD055', 'Dakota Bailey', 'MGR-F06'),
    ('FLD056', 'Jules Holland', 'MGR-F06'),
    ('FLD057', 'Avery Dixon', 'MGR-F04'),
    ('FLD058', 'Morgan Ferguson', 'MGR-F05'),
    ('FLD059', 'Jordan Rios', 'MGR-F06'),
    ('FLD060', 'Taylor Hartman', 'MGR-F04'),
    ('FLD061', 'Parker Bryant', 'MGR-F01'),
    ('FLD062', 'Riley Barrett', 'MGR-F04'),
    ('FLD063', 'Casey Sutton', 'MGR-F05'),
    ('FLD064', 'Cameron Wallace', 'MGR-F01'),
    ('FLD065', 'Quinn Kim', 'MGR-F06'),
    ('FLD066', 'Rowan Vega', 'MGR-F06'),
    ('FLD067', 'Jamie Montgomery', 'MGR-F01'),
    ('FLD068', 'Skyler Bowers', 'MGR-F05'),
    ('FLD069', 'Drew Cross', 'MGR-F04'),
    ('FLD070', 'Reese Rogers', 'MGR-F04'),
    ('FLD071', 'Emerson Larsen', 'MGR-F01'),
    ('FLD072', 'Hayden Brock', 'MGR-F06'),
    ('FLD073', 'Finley Powell', 'MGR-F05'),
    ('FLD074', 'Sage Hendrix', 'MGR-F01'),
    ('FLD075', 'Elliot Wright', 'MGR-F01'),
    ('FLD076', 'Blair Salazar', 'MGR-F01'),
    ('FLD077', 'Harper West', 'MGR-F04'),
    ('FLD078', 'Kendall Carrillo', 'MGR-F04');

-- ============================================================
-- 5. ASSIGN SIX INSIDE REPRESENTATIVES
--
-- Retrieve their actual IDs from zip_rep_assignment.
-- This avoids assuming a numbering convention.
-- ============================================================

WITH inside_reps AS (
    SELECT
        rep_id,
        ROW_NUMBER() OVER (ORDER BY rep_id) AS rn
    FROM (
        SELECT DISTINCT rep_id
        FROM core.zip_rep_assignment
        WHERE coverage_type = 'Inside'
    ) AS x
),
inside_names (rn, rep_name) AS (
    VALUES
        (1, 'Logan Navarro'),
        (2, 'Sydney Baldwin'),
        (3, 'Alex Knight'),
        (4, 'Charlie Phelps'),
        (5, 'Dakota Bradley'),
        (6, 'Jules Webb')
)
INSERT INTO core.sales_rep_organization
    (rep_id, rep_name, manager_id)
SELECT
    r.rep_id,
    n.rep_name,
    'MGR-I01'
FROM inside_reps AS r
JOIN inside_names AS n
    ON r.rn = n.rn;

-- ============================================================
-- 6. VALIDATE ORGANIZATION
--
-- Abort the transaction if representatives are missing,
-- misclassified, or incorrectly assigned.
-- ============================================================

DO $$
DECLARE
    v_total INTEGER;
    v_field INTEGER;
    v_inside INTEGER;
    v_exceptions INTEGER;
BEGIN

    SELECT
        COUNT(*),
        COUNT(*) FILTER (
            WHERE m.coverage_type = 'Field'
        ),
        COUNT(*) FILTER (
            WHERE m.coverage_type = 'Inside'
        )
    INTO
        v_total,
        v_field,
        v_inside
    FROM core.sales_rep_organization AS o
    JOIN core.sales_manager AS m
        ON o.manager_id = m.manager_id;

    IF v_total <> 84
       OR v_field <> 78
       OR v_inside <> 6
    THEN
        RAISE EXCEPTION
            'Rep count mismatch: Total %, Field %, Inside %',
            v_total, v_field, v_inside;
    END IF;

    SELECT COUNT(*)
    INTO v_exceptions
    FROM (
        (
            SELECT DISTINCT
                rep_id,
                coverage_type
            FROM core.zip_rep_assignment

            EXCEPT

            SELECT
                o.rep_id,
                m.coverage_type
            FROM core.sales_rep_organization AS o
            JOIN core.sales_manager AS m
                ON o.manager_id = m.manager_id
        )

        UNION ALL

        (
            SELECT
                o.rep_id,
                m.coverage_type
            FROM core.sales_rep_organization AS o
            JOIN core.sales_manager AS m
                ON o.manager_id = m.manager_id

            EXCEPT

            SELECT DISTINCT
                rep_id,
                coverage_type
            FROM core.zip_rep_assignment
        )
    ) AS mismatches;

    IF v_exceptions <> 0 THEN
        RAISE EXCEPTION
            'Rep ID / coverage mismatch: % exceptions',
            v_exceptions;
    END IF;

END $$;

-- ============================================================
-- 7. CREATE POWER BI ORGANIZATION DIMENSION
-- ============================================================

CREATE OR REPLACE VIEW analytics.dim_sales_organization AS

SELECT
    o.rep_id,
    o.rep_name,

    o.rep_id || ' - ' || o.rep_name
        AS rep_display,

    m.manager_id,
    m.manager_name,

    m.manager_id || ' - ' || m.manager_name
        AS manager_display,

    m.region_name,
    m.coverage_type

FROM core.sales_rep_organization AS o
JOIN core.sales_manager AS m
    ON o.manager_id = m.manager_id;

-- ============================================================
-- 8. SAVE ALL CHANGES
-- ============================================================

COMMIT;

-- ============================================================
-- 9. FINAL VALIDATION REPORT
-- ============================================================

SELECT
    manager_id,
    manager_name,
    region_name,
    coverage_type,
    COUNT(*) AS rep_count
FROM analytics.dim_sales_organization
GROUP BY
    manager_id,
    manager_name,
    region_name,
    coverage_type
ORDER BY manager_id;