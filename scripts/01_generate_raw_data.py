import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import string

np.random.seed(42)
random.seed(42)

# --- CONFIG ---
NUM_MEMBERS = 1200
NUM_LOANS = 2800
NUM_PAYMENTS = 35000

# --- MEMBERS TABLE (raw, with messy data) ---
first_names = ['James','Mary','Robert','Patricia','John','Jennifer','Michael','Linda','David','Elizabeth',
               'William','Barbara','Richard','Susan','Joseph','Jessica','Thomas','Sarah','Charles','Karen',
               'Christopher','Lisa','Daniel','Nancy','Matthew','Betty','Anthony','Margaret','Mark','Sandra',
               'Donald','Ashley','Steven','Dorothy','Paul','Kimberly','Andrew','Emily','Joshua','Donna',
               'Kenneth','Michelle','Kevin','Carol','Brian','Amanda','George','Melissa','Timothy','Deborah',
               'Ronald','Stephanie','Edward','Rebecca','Jason','Sharon','Jeffrey','Laura','Ryan','Cynthia',
               'Jacob','Kathleen','Gary','Amy','Nicholas','Angela','Eric','Shirley','Jonathan','Anna',
               'Stephen','Brenda','Larry','Pamela','Justin','Emma','Scott','Nicole','Brandon','Helen']

last_names = ['Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis','Rodriguez','Martinez',
              'Hernandez','Lopez','Gonzalez','Wilson','Anderson','Thomas','Taylor','Moore','Jackson','Martin',
              'Lee','Perez','Thompson','White','Harris','Sanchez','Clark','Ramirez','Lewis','Robinson',
              'Walker','Young','Allen','King','Wright','Scott','Torres','Nguyen','Hill','Flores',
              'Green','Adams','Nelson','Baker','Hall','Rivera','Campbell','Mitchell','Carter','Roberts']

cities_tx = ['Fort Worth','Arlington','Dallas','Denton','Weatherford','Granbury','Cleburne',
             'Mansfield','Burleson','Keller','Southlake','Grapevine','Bedford','Hurst','Euless',
             'North Richland Hills','Haltom City','Watauga','Benbrook','White Settlement']

member_ids = [f'MBR-{str(i).zfill(6)}' for i in range(1, NUM_MEMBERS + 1)]

members = []
for i, mid in enumerate(member_ids):
    fn = random.choice(first_names)
    ln = random.choice(last_names)
    join_date = datetime(2010, 1, 1) + timedelta(days=random.randint(0, 5400))
    city = random.choice(cities_tx)
    credit_score = int(np.clip(np.random.normal(680, 80), 350, 850))
    email = f"{fn.lower()}.{ln.lower()}{random.randint(1,999)}@{'gmail.com' if random.random() > 0.4 else 'yahoo.com'}"
    phone = f"({random.choice(['817','682','214','972'])}){random.randint(100,999)}-{random.randint(1000,9999)}"

    # Introduce messiness
    if random.random() < 0.03:
        fn = fn.upper()  # inconsistent casing
    if random.random() < 0.03:
        ln = '  ' + ln  # leading whitespace
    if random.random() < 0.05:
        email = ''  # missing email
    if random.random() < 0.04:
        phone = 'N/A'  # bad phone
    if random.random() < 0.02:
        credit_score = None  # missing credit score
    if random.random() < 0.015:
        mid_dup = mid  # will create a near-duplicate row
        members.append([mid_dup, fn, ln, join_date.strftime('%m/%d/%Y'), city, 'TX', credit_score, email, phone, 'Active'])

    status = random.choices(['Active', 'Inactive', 'Closed'], weights=[0.82, 0.12, 0.06])[0]
    members.append([mid, fn, ln, join_date.strftime('%m/%d/%Y'), city, 'TX', credit_score, email, phone, status])

members_df = pd.DataFrame(members, columns=[
    'member_id','first_name','last_name','join_date','city','state',
    'credit_score','email','phone','account_status'
])

# --- LOANS TABLE ---
loan_types = ['Auto Loan','Personal Loan','Mortgage','Home Equity','Credit Card','Student Loan']
loan_type_ranges = {
    'Auto Loan': (8000, 65000),
    'Personal Loan': (1000, 25000),
    'Mortgage': (80000, 450000),
    'Home Equity': (15000, 150000),
    'Credit Card': (500, 15000),
    'Student Loan': (5000, 80000),
}
loan_terms = {
    'Auto Loan': [36, 48, 60, 72],
    'Personal Loan': [12, 24, 36, 48],
    'Mortgage': [180, 240, 360],
    'Home Equity': [60, 120, 180],
    'Credit Card': [0],  # revolving
    'Student Loan': [120, 180, 240],
}

loans = []
loan_ids = []
for i in range(1, NUM_LOANS + 1):
    lid = f'LN-{str(i).zfill(7)}'
    loan_ids.append(lid)
    mid = random.choice(member_ids)
    ltype = random.choices(loan_types, weights=[30, 20, 15, 10, 15, 10])[0]
    lo, hi = loan_type_ranges[ltype]
    amount = round(random.uniform(lo, hi), 2)
    rate = round(random.uniform(3.5, 18.0) if ltype != 'Mortgage' else random.uniform(3.0, 7.5), 2)
    term = random.choice(loan_terms[ltype])
    origination = datetime(2018, 1, 1) + timedelta(days=random.randint(0, 2500))
    status = random.choices(['Current','Delinquent','Default','Paid Off'], weights=[0.65, 0.18, 0.05, 0.12])[0]

    # messy data
    if random.random() < 0.02:
        amount = -amount  # negative loan (data error)
    if random.random() < 0.03:
        rate = None
    if random.random() < 0.01:
        ltype = ltype.lower()  # inconsistent casing

    loans.append([lid, mid, ltype, amount, rate, term, origination.strftime('%Y-%m-%d'), status])

loans_df = pd.DataFrame(loans, columns=[
    'loan_id','member_id','loan_type','original_amount','interest_rate',
    'term_months','origination_date','loan_status'
])

# --- PAYMENTS TABLE ---
payment_statuses = ['On Time','Late','Missed','Partial']

payments = []
for i in range(1, NUM_PAYMENTS + 1):
    pid = f'PMT-{str(i).zfill(8)}'
    lid = random.choice(loan_ids)
    due_date = datetime(2022, 1, 1) + timedelta(days=random.randint(0, 1400))
    
    pstatus = random.choices(payment_statuses, weights=[0.62, 0.20, 0.10, 0.08])[0]
    
    loan_row = loans_df[loans_df['loan_id'] == lid].iloc[0]
    if loan_row['original_amount'] > 0:
        expected = round(loan_row['original_amount'] / max(loan_row['term_months'], 1), 2)
    else:
        expected = round(abs(loan_row['original_amount']) / 36, 2)
    expected = min(expected, 5000)  # cap for realism

    if pstatus == 'On Time':
        actual = expected
        pay_date = due_date + timedelta(days=random.randint(-5, 0))
    elif pstatus == 'Late':
        actual = expected
        pay_date = due_date + timedelta(days=random.randint(1, 45))
    elif pstatus == 'Missed':
        actual = 0.0
        pay_date = None
    else:  # Partial
        actual = round(expected * random.uniform(0.2, 0.8), 2)
        pay_date = due_date + timedelta(days=random.randint(-2, 15))

    # messy
    if random.random() < 0.02:
        pstatus = pstatus.upper()
    if random.random() < 0.01 and actual > 0:
        actual = -actual  # negative payment error

    pay_date_str = pay_date.strftime('%Y-%m-%d') if pay_date else ''

    payments.append([pid, lid, due_date.strftime('%Y-%m-%d'), pay_date_str, expected, actual, pstatus])

payments_df = pd.DataFrame(payments, columns=[
    'payment_id','loan_id','due_date','payment_date','expected_amount',
    'actual_amount','payment_status'
])

# --- SAVE RAW DATA ---
members_df.to_csv(r'C:\Users\Jonat\OneDrive\Documents\eecu_project\data\raw\raw_members.csv', index=False)
loans_df.to_csv(r'C:\Users\Jonat\OneDrive\Documents\eecu_project\data\raw\raw_loans.csv', index=False)
payments_df.to_csv(r'C:\Users\Jonat\OneDrive\Documents\eecu_project\data\raw\raw_payments.csv', index=False)

print(f"Generated {len(members_df)} member rows, {len(loans_df)} loan rows, {len(payments_df)} payment rows")
print(f"Intentional data issues seeded: duplicates, nulls, negative values, inconsistent casing, whitespace, bad phone numbers")
