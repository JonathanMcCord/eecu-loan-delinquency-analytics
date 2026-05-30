# Credit Union Loan Delinquency Analytics — End-to-End Pipeline

An end-to-end data analytics project simulating a mid-sized Texas credit union (modeled after the EECU service area). Generates realistic loan and payment data, cleans it with SQL, scores members for delinquency risk in Python, and surfaces the results in an interactive Power BI dashboard built for a collections team.

> **About this project:** This is a portfolio project that *simulates* a credit union analytics scenario using synthetic data. It is not built with real EECU data or affiliated with the institution — the name and DFW-area city list are used to ground the project in a recognizable regional context.

---

## Why this project

Lending institutions live or die on their ability to identify members heading toward delinquency *before* default. The collections team has limited time and staff, so the central question is practical: **which members are most at risk, and what do they have in common?**

This project demonstrates the full analyst workflow that answers that question — from intentionally messy raw data, through SQL cleaning and aggregation, through Python risk scoring, to a decision-ready Power BI dashboard a collections team could actually use to prioritize outreach.

---

## Key findings

The pipeline produced a complete risk-scored member dataset of **838 members with 3+ late or missed payments** flagged for collections attention, plus several segmentation views:

- **Delinquency by credit tier** — late payment rates across the five credit-score bands (300-749) plus an "Unknown" bucket for members with missing credit scores
- **Delinquency by loan type** — comparing risk across Auto, Personal, Mortgage, Home Equity, Credit Card, and Student loans, including total dollars at risk per category
- **Delinquency by city** — a 20-city DFW metroplex breakdown showing which markets carry the most concentrated risk
- **Monthly trend** — 47 months of delinquency-rate time series showing seasonality and direction
- **Member-level risk scoring** — a composite `risk_score` and `risk_tier` (Low / Moderate / High) assigned per member, ready for collections prioritization

### Dashboard

> 📷 *Power BI dashboard screenshot to be added — see `dashboard/EECU_Project.pbix` for the live file. The dashboard provides drill-through navigation, slicers by credit tier and city, and a member-level prioritization view.*

---

## Pipeline architecture

```
┌────────────────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  1. Generate raw   │ ──► │  2. SQL cleaning │ ──► │  3. Python scoring  │ ──► │  4. Power BI │
│  synthetic data    │     │  + aggregation   │     │  + tier assignment  │     │  dashboard   │
│  (intentional      │     │  (SQLite, in     │     │                     │     │              │
│  data quality      │     │  Python)         │     │  → CSV outputs       │     │              │
│  issues seeded)    │     │                  │     │                     │     │              │
└────────────────────┘     └──────────────────┘     └─────────────────────┘     └──────────────┘
   01_generate_raw_data.py    02_run_pipeline.py        02_run_pipeline.py            EECU_Project.pbix
                              (uses data_cleaning_and_analysis.sql)
```

Each stage is reproducible and orchestrated end-to-end through Python — running the two scripts in order regenerates the entire pipeline from scratch.

---

## Repository structure

```
eecu-loan-delinquency-analytics/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Files excluded from version control
├── scripts/
│   ├── 01_generate_raw_data.py        # Generates synthetic raw datasets
│   └── 02_run_pipeline.py             # SQL cleaning + Python risk scoring
├── sql/
│   └── data_cleaning_and_analysis.sql # Documented SQL reference (run via pipeline)
├── data/
│   ├── raw/                           # Synthetic raw input
│   │   ├── raw_members.csv            # 1,218 rows (incl. duplicates)
│   │   ├── raw_loans.csv              # 2,800 rows
│   │   └── raw_payments.csv           # 35,000 rows
│   └── processed/                     # Analysis outputs (Power BI inputs)
│       ├── delinquency_by_credit_tier.csv
│       ├── delinquency_by_loan_type.csv
│       ├── delinquency_by_city.csv
│       ├── monthly_delinquency_trend.csv
│       └── member_delinquency_scored.csv
├── dashboard/
│   └── EECU_Project.pbix              # Power BI dashboard
└── visuals/                           # Dashboard screenshots (to be added)
```

---

## Data quality challenges addressed

The synthetic raw data was deliberately seeded with the kinds of issues analysts encounter in production environments. The SQL cleaning pipeline addresses each of them:

1. **Duplicate member records** — A `ROW_NUMBER()` window function partitioned by `member_id` keeps the first occurrence and drops the rest.
2. **Inconsistent name casing and leading whitespace** — Names like "JAMES" and "  Smith" are normalized to proper case with whitespace trimmed.
3. **Missing critical fields (credit scores, interest rates)** — Rather than dropping these records, the pipeline preserves them with explicit boolean flags (`credit_score_missing`, `rate_missing`) so analysis can include or exclude them deliberately.
4. **Bad-format placeholder values** — Phone numbers stored as `'N/A'` and empty email strings are converted to `NULL` so downstream queries handle them consistently.
5. **Negative loan and payment amounts** — Sign-flipped values from data entry errors are corrected with `ABS()`.
6. **Inconsistent status casing** — Payment statuses like `'LATE'` vs `'Late'` are normalized so aggregation queries don't double-count.

---

## Risk scoring methodology

Beyond raw aggregations, the pipeline computes a member-level composite risk score that combines delinquency rate, missed payment count, and total dollars past due, then assigns each member to one of three tiers:

- **Low Risk** — score under 20
- **Moderate Risk** — score 20-40
- **High Risk** — score above 40

The output dataset (`member_delinquency_scored.csv`) is sorted by risk score and can be loaded directly into the dashboard or handed to the collections team as a prioritized outreach list.

---

## How to reproduce

```bash
# 1. Clone the repo
git clone https://github.com/JonathanMcCord/eecu-loan-delinquency-analytics.git
cd eecu-loan-delinquency-analytics

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate the synthetic raw data (creates files in data/raw/)
python scripts/01_generate_raw_data.py

# 4. Run the full pipeline (cleaning, scoring, exports)
python scripts/02_run_pipeline.py

# 5. Open the Power BI dashboard
# Open dashboard/EECU_Project.pbix in Power BI Desktop
# Data sources point to data/processed/*.csv files
```

**Note on file paths:** the original scripts use hardcoded Windows paths from the author's local environment. To run on a different machine, update the `BASE_DIR` constant at the top of each script to point to your local copy of this repo.

---

## Tech stack

- **Python** — pandas, NumPy for data generation, orchestration, and risk scoring
- **SQL** — SQLite (executed via Python `sqlite3`); window functions, CASE-WHEN logic, aggregation queries
- **Power BI** — interactive dashboard with slicers, drill-through navigation, and member-level views

---

## What this project demonstrates

- End-to-end pipeline design — raw data through to a decision-ready deliverable
- SQL fluency — cleaning, deduplication, aggregation, conditional logic
- Python orchestration — combining data generation, SQL execution, and downstream analysis in a reproducible script
- Risk modeling judgment — building a composite score that combines multiple signals into a single actionable tier
- BI dashboard design — translating analytical output into a tool a non-technical team can actually use
- Real-world data quality awareness — handling messy inputs the way production systems require

---

## About

Built by **Jonathan McCord** as a portfolio project demonstrating the full analyst workflow on a realistic credit union scenario.

- **LinkedIn:** [linkedin.com/in/jonathanamccord](https://www.linkedin.com/in/jonathanamccord)
- **GitHub:** [github.com/JonathanMcCord](https://github.com/JonathanMcCord)
