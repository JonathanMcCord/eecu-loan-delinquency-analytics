-- ============================================================
-- EECU LOAN DELINQUENCY ANALYSIS — DATA CLEANING QUERIES
-- ============================================================
-- Author: [Your Name]
-- Purpose: Clean raw member, loan, and payment data before
--          analysis and Power BI visualization.
--
-- These queries are written in standard SQL and executed via
-- Python (sqlite3) in the pipeline script. They demonstrate
-- data validation, cleaning, and transformation skills.
-- ============================================================


-- ============================================================
-- STEP 1: CLEAN MEMBERS TABLE
-- ============================================================

-- 1A: Remove duplicate member records (keep first occurrence)
-- Business rule: Each member_id should appear exactly once.

CREATE TABLE members_clean AS
SELECT *
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY ROWID) AS row_num
    FROM raw_members
)
WHERE row_num = 1;

-- Drop the helper column
ALTER TABLE members_clean DROP COLUMN row_num;


-- 1B: Standardize name casing and trim whitespace
-- Issue found: Some names are ALL CAPS, others have leading spaces.

UPDATE members_clean
SET first_name = UPPER(SUBSTR(TRIM(first_name), 1, 1)) ||
                 LOWER(SUBSTR(TRIM(first_name), 2)),
    last_name  = UPPER(SUBSTR(TRIM(last_name), 1, 1)) ||
                 LOWER(SUBSTR(TRIM(last_name), 2));


-- 1C: Flag and handle missing critical data
-- Issue found: ~2% of members have NULL credit scores.
-- Decision: Keep them but flag for review rather than dropping.

ALTER TABLE members_clean ADD COLUMN credit_score_missing INTEGER DEFAULT 0;

UPDATE members_clean
SET credit_score_missing = 1
WHERE credit_score IS NULL;


-- 1D: Standardize phone numbers — replace bad entries with NULL
-- Issue found: Some phone fields contain 'N/A' instead of being NULL.

UPDATE members_clean
SET phone = NULL
WHERE phone = 'N/A' OR phone = '' OR phone = 'n/a';


-- 1E: Standardize empty emails to NULL

UPDATE members_clean
SET email = NULL
WHERE email = '' OR email = ' ';


-- ============================================================
-- STEP 2: CLEAN LOANS TABLE
-- ============================================================

-- 2A: Fix negative loan amounts (data entry errors)
-- Business rule: Loan amounts must be positive.

CREATE TABLE loans_clean AS
SELECT * FROM raw_loans;

UPDATE loans_clean
SET original_amount = ABS(original_amount)
WHERE original_amount < 0;


-- 2B: Standardize loan type casing
-- Issue found: Some loan types are lowercase ('auto loan' vs 'Auto Loan').

UPDATE loans_clean
SET loan_type = UPPER(SUBSTR(loan_type, 1, 1)) || SUBSTR(loan_type, 2)
WHERE loan_type <> UPPER(SUBSTR(loan_type, 1, 1)) || SUBSTR(loan_type, 2);


-- 2C: Flag loans with missing interest rates

ALTER TABLE loans_clean ADD COLUMN rate_missing INTEGER DEFAULT 0;

UPDATE loans_clean
SET rate_missing = 1
WHERE interest_rate IS NULL;


-- ============================================================
-- STEP 3: CLEAN PAYMENTS TABLE
-- ============================================================

-- 3A: Standardize payment status casing
-- Issue found: Some statuses are ALL CAPS ('LATE' vs 'Late').

CREATE TABLE payments_clean AS
SELECT * FROM raw_payments;

UPDATE payments_clean
SET payment_status = UPPER(SUBSTR(payment_status, 1, 1)) ||
                     LOWER(SUBSTR(payment_status, 2));


-- 3B: Fix negative payment amounts

UPDATE payments_clean
SET actual_amount = ABS(actual_amount)
WHERE actual_amount < 0;


-- 3C: Set empty payment dates to NULL (missed payments)

UPDATE payments_clean
SET payment_date = NULL
WHERE payment_date = '' OR payment_date = ' ';


-- ============================================================
-- STEP 4: ANALYTICAL QUERIES (For Power BI dataset)
-- ============================================================

-- 4A: DELINQUENCY SUMMARY BY MEMBER
-- Uses GROUP BY + HAVING to find members with 3+ late/missed payments
-- This is the core query powering the dashboard.

CREATE TABLE member_delinquency AS
SELECT
    m.member_id,
    m.first_name || ' ' || m.last_name AS member_name,
    m.city,
    m.credit_score,
    m.account_status,
    COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) AS late_payment_count,
    COUNT(CASE WHEN p.payment_status = 'Missed' THEN 1 END) AS missed_payment_count,
    SUM(CASE WHEN p.payment_status IN ('Late', 'Missed')
             THEN p.expected_amount - p.actual_amount ELSE 0 END) AS total_amount_past_due,
    COUNT(p.payment_id) AS total_payments,
    ROUND(COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) * 100.0
          / COUNT(p.payment_id), 1) AS delinquency_rate
FROM members_clean m
JOIN loans_clean l ON m.member_id = l.member_id
JOIN payments_clean p ON l.loan_id = p.loan_id
WHERE m.account_status = 'Active'
GROUP BY m.member_id, member_name, m.city, m.credit_score, m.account_status
HAVING COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) >= 3;


-- 4B: DELINQUENCY BY LOAN TYPE
-- Which loan products have the most payment issues?

CREATE TABLE delinquency_by_loan_type AS
SELECT
    l.loan_type,
    COUNT(DISTINCT l.loan_id) AS total_loans,
    COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) AS late_payments,
    COUNT(p.payment_id) AS total_payments,
    ROUND(COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) * 100.0
          / COUNT(p.payment_id), 1) AS delinquency_rate_pct,
    SUM(CASE WHEN p.payment_status IN ('Late', 'Missed')
             THEN p.expected_amount - p.actual_amount ELSE 0 END) AS amount_at_risk
FROM loans_clean l
JOIN payments_clean p ON l.loan_id = p.loan_id
GROUP BY l.loan_type
ORDER BY delinquency_rate_pct DESC;


-- 4C: MONTHLY DELINQUENCY TREND
-- How are late payments trending over time?

CREATE TABLE monthly_delinquency_trend AS
SELECT
    SUBSTR(p.due_date, 1, 7) AS month,
    COUNT(p.payment_id) AS total_payments,
    COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) AS late_payments,
    ROUND(COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) * 100.0
          / COUNT(p.payment_id), 1) AS delinquency_rate_pct
FROM payments_clean p
GROUP BY SUBSTR(p.due_date, 1, 7)
ORDER BY month;


-- 4D: CREDIT SCORE DISTRIBUTION OF DELINQUENT MEMBERS
-- Are late payments concentrated in lower credit score ranges?

CREATE TABLE delinquency_by_credit_tier AS
SELECT
    CASE
        WHEN m.credit_score >= 750 THEN '750+ (Excellent)'
        WHEN m.credit_score >= 700 THEN '700-749 (Good)'
        WHEN m.credit_score >= 650 THEN '650-699 (Fair)'
        WHEN m.credit_score >= 600 THEN '600-649 (Below Avg)'
        WHEN m.credit_score IS NOT NULL THEN 'Below 600 (Poor)'
        ELSE 'Unknown'
    END AS credit_tier,
    COUNT(DISTINCT m.member_id) AS member_count,
    SUM(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 ELSE 0 END) AS late_payments,
    COUNT(p.payment_id) AS total_payments,
    ROUND(SUM(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 ELSE 0 END) * 100.0
          / COUNT(p.payment_id), 1) AS delinquency_rate_pct
FROM members_clean m
JOIN loans_clean l ON m.member_id = l.member_id
JOIN payments_clean p ON l.loan_id = p.loan_id
GROUP BY credit_tier
ORDER BY delinquency_rate_pct DESC;


-- 4E: TOP CITIES BY DELINQUENCY (DFW Metroplex breakdown)

CREATE TABLE delinquency_by_city AS
SELECT
    m.city,
    COUNT(DISTINCT m.member_id) AS member_count,
    COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) AS late_payments,
    COUNT(p.payment_id) AS total_payments,
    ROUND(COUNT(CASE WHEN p.payment_status IN ('Late', 'Missed') THEN 1 END) * 100.0
          / COUNT(p.payment_id), 1) AS delinquency_rate_pct
FROM members_clean m
JOIN loans_clean l ON m.member_id = l.member_id
JOIN payments_clean p ON l.loan_id = p.loan_id
GROUP BY m.city
ORDER BY delinquency_rate_pct DESC;
