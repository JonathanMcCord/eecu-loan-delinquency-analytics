import sqlite3
import pandas as pd
import os

# --- PATHS ---
BASE_DIR = r'C:\Users\Jonat\OneDrive\Documents\eecu_project'
RAW_DIR = os.path.join(BASE_DIR, 'data', 'raw')
CLEAN_DIR = os.path.join(BASE_DIR, 'data', 'cleaned')
SQL_DIR = os.path.join(BASE_DIR, 'sql')
DB_PATH = os.path.join(BASE_DIR, 'data', 'eecu_analysis.db')

os.makedirs(CLEAN_DIR, exist_ok=True)


def load_raw_data(conn):
    """Load raw CSVs into SQLite tables."""
    print("Loading raw data into SQLite...")

    members = pd.read_csv(os.path.join(RAW_DIR, 'raw_members.csv'))
    loans = pd.read_csv(os.path.join(RAW_DIR, 'raw_loans.csv'))
    payments = pd.read_csv(os.path.join(RAW_DIR, 'raw_payments.csv'))

    members.to_sql('raw_members', conn, if_exists='replace', index=False)
    loans.to_sql('raw_loans', conn, if_exists='replace', index=False)
    payments.to_sql('raw_payments', conn, if_exists='replace', index=False)

    print(f"  Members:  {len(members):,} rows")
    print(f"  Loans:    {len(loans):,} rows")
    print(f"  Payments: {len(payments):,} rows")


def run_sql_cleaning(conn):
    """Execute SQL cleaning and analysis using inline statements for SQLite compatibility."""
    print("\nRunning SQL data cleaning & analysis...")
    cur = conn.cursor()

    # --- STEP 1: CLEAN MEMBERS ---
    # 1A: Deduplicate members
    cur.execute("""
        CREATE TABLE members_clean AS
        SELECT member_id, first_name, last_name, join_date, city, state,
               credit_score, email, phone, account_status
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY ROWID) AS rn
            FROM raw_members
        ) WHERE rn = 1
    """)

    # 1B: Standardize names
    cur.execute("""
        UPDATE members_clean
        SET first_name = UPPER(SUBSTR(TRIM(first_name), 1, 1)) || LOWER(SUBSTR(TRIM(first_name), 2)),
            last_name  = UPPER(SUBSTR(TRIM(last_name), 1, 1))  || LOWER(SUBSTR(TRIM(last_name), 2))
    """)

    # 1C: Flag missing credit scores
    cur.execute("ALTER TABLE members_clean ADD COLUMN credit_score_missing INTEGER DEFAULT 0")
    cur.execute("UPDATE members_clean SET credit_score_missing = 1 WHERE credit_score IS NULL")

    # 1D: Standardize bad phone/email to NULL
    cur.execute("UPDATE members_clean SET phone = NULL WHERE phone IN ('N/A','n/a','') OR phone IS NULL")
    cur.execute("UPDATE members_clean SET email = NULL WHERE email IN ('',' ') OR email IS NULL")

    # --- STEP 2: CLEAN LOANS ---
    cur.execute("CREATE TABLE loans_clean AS SELECT * FROM raw_loans")
    cur.execute("UPDATE loans_clean SET original_amount = ABS(original_amount) WHERE original_amount < 0")
    cur.execute("""
        UPDATE loans_clean
        SET loan_type = UPPER(SUBSTR(loan_type, 1, 1)) || SUBSTR(loan_type, 2)
    """)
    cur.execute("ALTER TABLE loans_clean ADD COLUMN rate_missing INTEGER DEFAULT 0")
    cur.execute("UPDATE loans_clean SET rate_missing = 1 WHERE interest_rate IS NULL")

    # --- STEP 3: CLEAN PAYMENTS ---
    cur.execute("CREATE TABLE payments_clean AS SELECT * FROM raw_payments")
    cur.execute("""
        UPDATE payments_clean
        SET payment_status = UPPER(SUBSTR(payment_status, 1, 1)) || LOWER(SUBSTR(payment_status, 2))
    """)
    cur.execute("UPDATE payments_clean SET actual_amount = ABS(actual_amount) WHERE actual_amount < 0")
    cur.execute("UPDATE payments_clean SET payment_date = NULL WHERE payment_date IN ('',' ')")

    # --- STEP 4: ANALYTICAL TABLES ---

    # 4A: Member delinquency (the core GROUP BY + HAVING query)
    cur.execute("""
        CREATE TABLE member_delinquency AS
        SELECT
            m.member_id,
            m.first_name || ' ' || m.last_name AS member_name,
            m.city,
            m.credit_score,
            m.account_status,
            COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) AS late_payment_count,
            COUNT(CASE WHEN p.payment_status = 'Missed' THEN 1 END) AS missed_payment_count,
            SUM(CASE WHEN p.payment_status IN ('Late','Missed')
                     THEN p.expected_amount - p.actual_amount ELSE 0 END) AS total_amount_past_due,
            COUNT(p.payment_id) AS total_payments,
            ROUND(COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) * 100.0
                  / COUNT(p.payment_id), 1) AS delinquency_rate
        FROM members_clean m
        JOIN loans_clean l ON m.member_id = l.member_id
        JOIN payments_clean p ON l.loan_id = p.loan_id
        WHERE m.account_status = 'Active'
        GROUP BY m.member_id, member_name, m.city, m.credit_score, m.account_status
        HAVING COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) >= 3
    """)

    # 4B: Delinquency by loan type
    cur.execute("""
        CREATE TABLE delinquency_by_loan_type AS
        SELECT
            l.loan_type,
            COUNT(DISTINCT l.loan_id) AS total_loans,
            COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) AS late_payments,
            COUNT(p.payment_id) AS total_payments,
            ROUND(COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) * 100.0
                  / COUNT(p.payment_id), 1) AS delinquency_rate_pct,
            SUM(CASE WHEN p.payment_status IN ('Late','Missed')
                     THEN p.expected_amount - p.actual_amount ELSE 0 END) AS amount_at_risk
        FROM loans_clean l
        JOIN payments_clean p ON l.loan_id = p.loan_id
        GROUP BY l.loan_type
        ORDER BY delinquency_rate_pct DESC
    """)

    # 4C: Monthly trend
    cur.execute("""
        CREATE TABLE monthly_delinquency_trend AS
        SELECT
            SUBSTR(p.due_date, 1, 7) AS month,
            COUNT(p.payment_id) AS total_payments,
            COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) AS late_payments,
            ROUND(COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) * 100.0
                  / COUNT(p.payment_id), 1) AS delinquency_rate_pct
        FROM payments_clean p
        GROUP BY SUBSTR(p.due_date, 1, 7)
        ORDER BY month
    """)

    # 4D: Credit tier breakdown
    cur.execute("""
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
            SUM(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 ELSE 0 END) AS late_payments,
            COUNT(p.payment_id) AS total_payments,
            ROUND(SUM(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 ELSE 0 END) * 100.0
                  / COUNT(p.payment_id), 1) AS delinquency_rate_pct
        FROM members_clean m
        JOIN loans_clean l ON m.member_id = l.member_id
        JOIN payments_clean p ON l.loan_id = p.loan_id
        GROUP BY credit_tier
        ORDER BY delinquency_rate_pct DESC
    """)

    # 4E: City breakdown
    cur.execute("""
        CREATE TABLE delinquency_by_city AS
        SELECT
            m.city,
            COUNT(DISTINCT m.member_id) AS member_count,
            COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) AS late_payments,
            COUNT(p.payment_id) AS total_payments,
            ROUND(COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) * 100.0
                  / COUNT(p.payment_id), 1) AS delinquency_rate_pct
        FROM members_clean m
        JOIN loans_clean l ON m.member_id = l.member_id
        JOIN payments_clean p ON l.loan_id = p.loan_id
        GROUP BY m.city
        ORDER BY delinquency_rate_pct DESC
    """)

    # 4F: Member loan summary (for drill-through: loan breakdown per member)
    cur.execute("""
        CREATE TABLE member_loan_summary AS
        SELECT
            m.member_id,
            m.first_name || ' ' || m.last_name AS member_name,
            l.loan_id,
            l.loan_type,
            l.original_amount,
            l.interest_rate,
            l.loan_status,
            l.origination_date,
            COUNT(p.payment_id) AS total_payments,
            COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) AS late_payments,
            COUNT(CASE WHEN p.payment_status = 'Missed' THEN 1 END) AS missed_payments,
            SUM(CASE WHEN p.payment_status IN ('Late','Missed')
                     THEN p.expected_amount - p.actual_amount ELSE 0 END) AS amount_past_due,
            ROUND(COUNT(CASE WHEN p.payment_status IN ('Late','Missed') THEN 1 END) * 100.0
                  / COUNT(p.payment_id), 1) AS loan_delinquency_rate
        FROM members_clean m
        JOIN loans_clean l ON m.member_id = l.member_id
        JOIN payments_clean p ON l.loan_id = p.loan_id
        GROUP BY m.member_id, member_name, l.loan_id, l.loan_type,
                 l.original_amount, l.interest_rate, l.loan_status, l.origination_date
    """)

    # 4G: Payment detail (for drill-through: every payment row with member info)
    cur.execute("""
        CREATE TABLE payment_detail AS
        SELECT
            m.member_id,
            m.first_name || ' ' || m.last_name AS member_name,
            l.loan_id,
            l.loan_type,
            p.payment_id,
            p.due_date,
            p.payment_date,
            p.expected_amount,
            p.actual_amount,
            p.expected_amount - p.actual_amount AS shortfall,
            p.payment_status,
            CASE
                WHEN p.payment_date IS NULL THEN NULL
                WHEN p.payment_date > p.due_date
                    THEN CAST(julianday(p.payment_date) - julianday(p.due_date) AS INTEGER)
                ELSE 0
            END AS days_late
        FROM members_clean m
        JOIN loans_clean l ON m.member_id = l.member_id
        JOIN payments_clean p ON l.loan_id = p.loan_id
        ORDER BY m.member_id, p.due_date
    """)

    conn.commit()
    print("  SQL cleaning complete.")


def validate_cleaned_data(conn):
    """Run validation checks on cleaned data and print a report."""
    print("\n--- DATA QUALITY REPORT ---")

    # Members
    total = conn.execute("SELECT COUNT(*) FROM members_clean").fetchone()[0]
    dupes_removed = conn.execute("SELECT COUNT(*) FROM raw_members").fetchone()[0] - total
    missing_credit = conn.execute("SELECT COUNT(*) FROM members_clean WHERE credit_score_missing = 1").fetchone()[0]
    missing_email = conn.execute("SELECT COUNT(*) FROM members_clean WHERE email IS NULL").fetchone()[0]
    missing_phone = conn.execute("SELECT COUNT(*) FROM members_clean WHERE phone IS NULL").fetchone()[0]

    print(f"\nMEMBERS TABLE:")
    print(f"  Total clean records:       {total:,}")
    print(f"  Duplicate rows removed:    {dupes_removed}")
    print(f"  Missing credit scores:     {missing_credit}")
    print(f"  Missing emails:            {missing_email}")
    print(f"  Missing phone numbers:     {missing_phone}")

    # Loans
    neg_fixed = conn.execute("SELECT COUNT(*) FROM raw_loans WHERE original_amount < 0").fetchone()[0]
    missing_rate = conn.execute("SELECT COUNT(*) FROM loans_clean WHERE rate_missing = 1").fetchone()[0]

    print(f"\nLOANS TABLE:")
    print(f"  Negative amounts corrected: {neg_fixed}")
    print(f"  Missing interest rates:     {missing_rate}")

    # Payments
    neg_pmts = conn.execute("SELECT COUNT(*) FROM raw_payments WHERE actual_amount < 0").fetchone()[0]

    print(f"\nPAYMENTS TABLE:")
    print(f"  Negative payments fixed:    {neg_pmts}")

    # Delinquency highlights
    flagged = conn.execute("SELECT COUNT(*) FROM member_delinquency").fetchone()[0]
    worst = conn.execute(
        "SELECT member_name, late_payment_count FROM member_delinquency ORDER BY late_payment_count DESC LIMIT 1"
    ).fetchone()

    print(f"\nDELINQUENCY ANALYSIS:")
    print(f"  Members flagged (3+ late):  {flagged}")
    if worst:
        print(f"  Highest delinquency:        {worst[0]} ({worst[1]} late payments)")


def python_enrichment(conn):
    """Additional analysis using pandas that goes beyond SQL."""
    print("\nRunning Python enrichment analysis...")

    # Load the delinquency data
    delinq = pd.read_sql("SELECT * FROM member_delinquency", conn)

    # Calculate risk score (Python-side computation)
    # Weighted score: late payments (40%), missed payments (30%),
    # amount past due (20%), delinquency rate (10%)
    delinq['late_pmt_norm'] = (delinq['late_payment_count'] - delinq['late_payment_count'].min()) / \
                               (delinq['late_payment_count'].max() - delinq['late_payment_count'].min() + 1)
    delinq['missed_pmt_norm'] = (delinq['missed_payment_count'] - delinq['missed_payment_count'].min()) / \
                                 (delinq['missed_payment_count'].max() - delinq['missed_payment_count'].min() + 1)
    delinq['amt_due_norm'] = (delinq['total_amount_past_due'] - delinq['total_amount_past_due'].min()) / \
                              (delinq['total_amount_past_due'].max() - delinq['total_amount_past_due'].min() + 1)
    delinq['rate_norm'] = delinq['delinquency_rate'] / 100

    delinq['risk_score'] = round(
        (delinq['late_pmt_norm'] * 0.4 +
         delinq['missed_pmt_norm'] * 0.3 +
         delinq['amt_due_norm'] * 0.2 +
         delinq['rate_norm'] * 0.1) * 100, 1
    )

    # Assign risk tier
    delinq['risk_tier'] = pd.cut(
        delinq['risk_score'],
        bins=[0, 25, 50, 75, 100],
        labels=['Low Risk', 'Moderate Risk', 'High Risk', 'Critical Risk'],
        include_lowest=True
    )

    # Drop helper columns
    delinq.drop(columns=['late_pmt_norm', 'missed_pmt_norm', 'amt_due_norm', 'rate_norm'], inplace=True)

    delinq.to_sql('member_delinquency_scored', conn, if_exists='replace', index=False)
    print(f"  Risk scores calculated for {len(delinq)} members")
    print(f"  Risk tier breakdown:")
    print(delinq['risk_tier'].value_counts().to_string())


def export_for_powerbi(conn):
    """Export all analytical tables as CSVs for Power BI import."""
    print("\nExporting datasets for Power BI...")

    tables_to_export = [
        'member_delinquency_scored',
        'delinquency_by_loan_type',
        'monthly_delinquency_trend',
        'delinquency_by_credit_tier',
        'delinquency_by_city',
        'member_loan_summary',
        'payment_detail',
        'members_clean',
        'loans_clean',
    ]

    for table in tables_to_export:
        df = pd.read_sql(f"SELECT * FROM {table}", conn)
        filepath = os.path.join(CLEAN_DIR, f"{table}.csv")
        df.to_csv(filepath, index=False)
        print(f"  Exported: {table}.csv ({len(df):,} rows)")


# --- MAIN PIPELINE ---
if __name__ == '__main__':
    print("=" * 60)
    print("EECU LOAN DELINQUENCY — DATA PIPELINE")
    print("=" * 60)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    load_raw_data(conn)
    run_sql_cleaning(conn)
    validate_cleaned_data(conn)
    python_enrichment(conn)
    export_for_powerbi(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"Clean CSVs ready for Power BI in: data/cleaned/")
    print("=" * 60)
