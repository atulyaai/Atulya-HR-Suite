import sqlite3
import os
from datetime import datetime, date, timedelta
from calendar import monthrange

DB_PATH = None

def get_db_path():
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = os.environ.get(
            "ATULYA_HR_DB",
            os.path.join(os.path.expanduser("~"), ".atulya_hr", "atulya_hr.db"),
        )
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH

def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            date_of_birth TEXT,
            gender TEXT,
            pan TEXT,
            uan TEXT,
            esi_number TEXT,
            bank_name TEXT,
            bank_account TEXT,
            ifsc_code TEXT,
            date_of_joining TEXT NOT NULL,
            date_of_relieving TEXT,
            department TEXT,
            designation TEXT,
            location TEXT,
            state TEXT DEFAULT 'Karnataka',
            basic_pay REAL DEFAULT 0,
            da REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            conveyance_allowance REAL DEFAULT 0,
            medical_allowance REAL DEFAULT 0,
            special_allowance REAL DEFAULT 0,
            other_allowance REAL DEFAULT 0,
            pf_number TEXT,
            pt_state TEXT DEFAULT 'Karnataka',
            tax_regime TEXT DEFAULT 'old',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present','absent','half-day','leave','holiday','weekoff')),
            in_time TEXT,
            out_time TEXT,
            remarks TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            UNIQUE(employee_id, date)
        );

        CREATE TABLE IF NOT EXISTS leave_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            days_per_year REAL NOT NULL,
            carry_forward REAL DEFAULT 0,
            requires_approval INTEGER DEFAULT 1,
            pay_affected INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS leave_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            financial_year TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            opening REAL DEFAULT 0,
            credited REAL DEFAULT 0,
            used REAL DEFAULT 0,
            lapsed REAL DEFAULT 0,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            UNIQUE(employee_id, financial_year, leave_type)
        );

        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            total_days REAL NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','cancelled')),
            approved_by TEXT,
            approved_on TEXT,
            applied_on TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            basic_pay REAL DEFAULT 0,
            da REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            conveyance_allowance REAL DEFAULT 0,
            medical_allowance REAL DEFAULT 0,
            special_allowance REAL DEFAULT 0,
            other_allowance REAL DEFAULT 0,
            gross_pay REAL DEFAULT 0,
            pf_employee REAL DEFAULT 0,
            pf_employer REAL DEFAULT 0,
            esi_employee REAL DEFAULT 0,
            esi_employer REAL DEFAULT 0,
            pt REAL DEFAULT 0,
            tds REAL DEFAULT 0,
            leave_deduction REAL DEFAULT 0,
            arrears REAL DEFAULT 0,
            other_deductions REAL DEFAULT 0,
            total_deductions REAL DEFAULT 0,
            net_pay REAL DEFAULT 0,
            total_days INTEGER DEFAULT 0,
            paid_days INTEGER DEFAULT 0,
            employer_contribution REAL DEFAULT 0,
            ctc REAL DEFAULT 0,
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft','processed','paid','cancelled')),
            processed_on TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
            UNIQUE(employee_id, month, year)
        );

        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'public' CHECK(type IN ('public','restricted','optional'))
        );

        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            relieving_date TEXT NOT NULL,
            notice_pay_days INTEGER DEFAULT 0,
            notice_pay_amount REAL DEFAULT 0,
            leave_encashment_days REAL DEFAULT 0,
            leave_encashment_amount REAL DEFAULT 0,
            gratuity_years INTEGER DEFAULT 0,
            gratuity_amount REAL DEFAULT 0,
            salary_due_amount REAL DEFAULT 0,
            other_payments REAL DEFAULT 0,
            pf_settlement REAL DEFAULT 0,
            loan_deduction REAL DEFAULT 0,
            other_deductions REAL DEFAULT 0,
            net_settlement REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            created_on TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );
    """)
    cur.execute("SELECT COUNT(*) FROM leave_types")
    if cur.fetchone()[0] == 0:
        cur.executescript("""
            INSERT INTO leave_types (code, name, days_per_year, carry_forward, requires_approval, pay_affected) VALUES
            ('EL', 'Earned Leave', 15, 30, 1, 0),
            ('CL', 'Casual Leave', 12, 0, 1, 0),
            ('SL', 'Sick Leave', 12, 0, 1, 0),
            ('LWP', 'Leave Without Pay', 0, 0, 1, 1);
        """)
    conn.commit()
    conn.close()

def indian_format(amount):
    if amount is None:
        return "0"
    amount = int(round(amount))
    s = str(amount)
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    groups = []
    while len(rest) > 2:
        groups.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.append(rest)
    groups.reverse()
    return ",".join(groups) + "," + last3

def financial_year(date_obj=None):
    if date_obj is None:
        date_obj = date.today()
    yr = date_obj.year
    if date_obj.month >= 4:
        return f"{yr}-{yr+1}"
    return f"{yr-1}-{yr}"

def financial_year_range(fy_str):
    parts = fy_str.split("-")
    start_yr = int(parts[0])
    end_yr = int(parts[1])
    return (date(start_yr, 4, 1), date(end_yr, 3, 31))

def month_boundaries(year, month):
    _, last_day = monthrange(year, month)
    return (date(year, month, 1), date(year, month, last_day))

def days_in_month(year, month):
    return monthrange(year, month)[1]

def first_day_of_month(year, month):
    return date(year, month, 1)

def last_day_of_month(year, month):
    _, last = monthrange(year, month)
    return date(year, month, last)

PF_WAGE_CEILING = 15000
EPS_WAGE_CEILING = 15000
EPS_CONTRIBUTION_RATE = 8.33
EPF_EMPLOYEE_RATE = 12.0
EPF_EMPLOYER_RATE = 12.0
EDLIS_RATE = 0.5
ADMIN_CHARGES_RATE = 0.5

ESI_WAGE_CEILING = 21000
ESI_EMPLOYEE_RATE = 0.75
ESI_EMPLOYER_RATE = 3.25

GRATUITY_DAYS = 15
GRATUITY_MONTHS = 26

def get_pf_wages(basic, da):
    wages = basic + da
    return min(wages, PF_WAGE_CEILING)

def calculate_pf(basic, da):
    pf_wages = get_pf_wages(basic, da)
    employee_pf = round(pf_wages * EPF_EMPLOYEE_RATE / 100, 2)
    employer_eps = round(min(pf_wages * EPS_CONTRIBUTION_RATE / 100, 1250), 2)
    employer_epf = round(pf_wages * EPF_EMPLOYER_RATE / 100 - employer_eps, 2)
    employer_edlis = round(pf_wages * EDLIS_RATE / 100, 2)
    employer_total = round(employer_epf + employer_eps + employer_edlis, 2)
    return {
        "employee": employee_pf,
        "employer_epf": employer_epf,
        "employer_eps": employer_eps,
        "employer_edlis": employer_edlis,
        "employer_total": employer_total,
    }

def calculate_esi(gross_pay):
    if gross_pay <= ESI_WAGE_CEILING:
        employee = round(gross_pay * ESI_EMPLOYEE_RATE / 100, 2)
        employer = round(gross_pay * ESI_EMPLOYER_RATE / 100, 2)
        return {"employee": employee, "employer": employer, "applicable": True}
    return {"employee": 0, "employer": 0, "applicable": False}

PT_SLABS = {
    "Karnataka": [
        (15000, 0),
        (20000, 150),
        (25000, 200),
        (30000, 300),
        (35000, 450),
        (40000, 600),
        (50000, 750),
        (60000, 900),
        (75000, 1000),
        (100000, 1100),
        (float("inf"), 1200),
    ],
    "Maharashtra": [
        (10000, 0),
        (15000, 175),
        (25000, 300),
        (35000, 450),
        (50000, 600),
        (75000, 750),
        (100000, 900),
        (float("inf"), 1000),
    ],
    "Tamil Nadu": [
        (2100, 0),
        (4500, 60),
        (6000, 115),
        (9000, 170),
        (12000, 230),
        (15000, 290),
        (25000, 360),
        (40000, 430),
        (60000, 510),
        (100000, 660),
        (float("inf"), 770),
    ],
    "Delhi": [
        (25000, 0),
        (30000, 125),
        (40000, 175),
        (55000, 250),
        (75000, 375),
        (100000, 500),
        (float("inf"), 625),
    ],
    "Telangana": [
        (15000, 0),
        (20000, 150),
        (25000, 200),
        (30000, 300),
        (40000, 400),
        (50000, 500),
        (60000, 600),
        (75000, 750),
        (100000, 1000),
        (float("inf"), 1100),
    ],
}

def get_pt(gross_pay, state="Karnataka"):
    slabs = PT_SLABS.get(state, PT_SLABS["Karnataka"])
    for limit, tax in slabs:
        if gross_pay <= limit:
            return tax
    return 0

TDS_OLD_REGIME = [
    (250000, 0, 0),
    (500000, 5, 12500),
    (1000000, 20, 100000),
    (float("inf"), 30, 0),
]

TDS_NEW_REGIME = [
    (300000, 0, 0),
    (600000, 5, 15000),
    (900000, 10, 45000),
    (1200000, 15, 90000),
    (1500000, 20, 150000),
    (float("inf"), 30, 0),
]

REBATE_87A_LIMIT = 500000
REBATE_87A_AMOUNT = 12500
HEALTH_EDUCATION_CESS = 4
STANDARD_DEDUCTION = 50000

def calculate_tds(yearly_taxable_income, regime="old", age="below60"):
    taxable = max(0, yearly_taxable_income - STANDARD_DEDUCTION)
    slabs = TDS_OLD_REGIME if regime == "old" else TDS_NEW_REGIME
    tax = 0
    prev_limit = 0
    for limit, rate, _ in slabs:
        if taxable > prev_limit:
            slab_amount = min(taxable, limit) - prev_limit
            tax += slab_amount * rate / 100
        prev_limit = limit
        if taxable <= limit:
            break
    if regime == "old" and taxable <= REBATE_87A_LIMIT:
        tax = max(0, tax - REBATE_87A_AMOUNT)
    cess = tax * HEALTH_EDUCATION_CESS / 100
    return round(tax + cess, 2)

def monthly_tds(yearly_taxable_income, regime="old", age="below60"):
    return round(calculate_tds(yearly_taxable_income, regime, age) / 12, 2)

def calculate_gratuity(basic, da, years_of_service):
    if years_of_service < 5:
        return 0
    last_drawn = basic + da
    gratuity = last_drawn * GRATUITY_DAYS * years_of_service / GRATUITY_MONTHS
    return round(gratuity, 2)

def calculate_leave_encashment(basic, da, unused_days):
    daily_rate = (basic + da) / 30
    return round(daily_rate * unused_days, 2)

def calculate_notice_pay(basic, da, hra, notice_days):
    monthly = basic + da + hra
    return round(monthly / 30 * notice_days, 2)
