
-- Industrial Sales Operations Analytics
-- Phase 6: Analyze 2025 ZIP-level net posted sales
--
-- Revenue follows the transaction's ship-to location.
-- Returns reduce revenue in their posting month.
-- This query is read-only.

WITH zip_sales AS (
    SELECT
        s.zip_code,
        COUNT(*) AS transaction_count,
        COUNT(*) FILTER (
            WHERE t.transaction_type = 'SHIPMENT'
        ) AS shipment_count,
        COUNT(*) FILTER (
            WHERE t.transaction_type = 'RETURN'
        ) AS return_count,
        SUM(t.posted_sales_amount) AS net_sales_2025

    FROM core.sales_transaction AS t

    INNER JOIN core.ship_to AS s
        ON t.ship_to_id = s.ship_to_id

    WHERE t.posting_date >= DATE '2025-01-01'
      AND t.posting_date < DATE '2026-01-01'

    GROUP BY s.zip_code
),

zip_classification AS (
    SELECT
        zip_code,
        transaction_count,
        shipment_count,
        return_count,
        net_sales_2025,

        CASE
            WHEN net_sales_2025 >= 200000
                THEN 'FIELD'
            ELSE 'INSIDE'
        END AS sales_channel

    FROM zip_sales
)

SELECT
    sales_channel,
    COUNT(*) AS active_zip_count,
    SUM(transaction_count) AS transaction_count,
    SUM(shipment_count) AS shipment_count,
    SUM(return_count) AS return_count,
    SUM(net_sales_2025) AS net_sales_2025,
    MIN(net_sales_2025) AS minimum_zip_sales,
    MAX(net_sales_2025) AS maximum_zip_sales,
    ROUND(AVG(net_sales_2025), 2) AS average_zip_sales

FROM zip_classification

GROUP BY sales_channel
ORDER BY sales_channel;
