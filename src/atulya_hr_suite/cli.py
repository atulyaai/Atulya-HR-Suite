import click
import os
import sys
from datetime import datetime, date
from functools import wraps
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from .utils import init_db, get_connection, indian_format, financial_year
from .core import (
    EmployeeManager, AttendanceManager, LeaveManager,
    PayrollManager, StatutoryManager, SettlementManager,
)

console = Console()

def db_context(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        init_db()
        return f(*args, **kwargs)
    return wrapper


@click.group()
def main():
    pass


@main.group()
def employee():
    pass


@employee.command(name="add")
@click.option("--code", "-c", required=True, help="Employee code")
@click.option("--first-name", "-f", required=True, help="First name")
@click.option("--last-name", "-l", required=True, help="Last name")
@click.option("--doj", required=True, help="Date of joining (YYYY-MM-DD)")
@click.option("--dept", help="Department")
@click.option("--designation", help="Designation")
@click.option("--basic", type=float, default=0, help="Basic pay")
@click.option("--da", type=float, default=0, help="Dearness Allowance")
@click.option("--hra", type=float, default=0, help="HRA")
@click.option("--pan", help="PAN number")
@click.option("--uan", help="UAN number")
@click.option("--bank", help="Bank name")
@click.option("--account", help="Bank account number")
@click.option("--ifsc", help="IFSC code")
@click.option("--state", default="Karnataka", help="State for PT")
@click.option("--regime", type=click.Choice(["old", "new"]), default="old", help="Tax regime")
@db_context
def add_employee(code, first_name, last_name, doj, dept, designation,
                 basic, da, hra, pan, uan, bank, account, ifsc, state, regime):
    mgr = EmployeeManager()
    emp_id = mgr.add(
        employee_code=code, first_name=first_name, last_name=last_name,
        date_of_joining=doj, department=dept, designation=designation,
        basic_pay=basic, da=da, hra=hra, pan=pan, uan=uan,
        bank_name=bank, bank_account=account, ifsc_code=ifsc,
        pt_state=state, tax_regime=regime,
    )
    if emp_id:
        console.print(f"[green]Employee added with ID: {emp_id}[/green]")
    else:
        console.print("[red]Error: Employee code already exists[/red]")
        sys.exit(1)


@employee.command(name="list")
@click.option("--status", default="active", help="Filter by status")
@click.option("--dept", help="Filter by department")
@db_context
def list_employees(status, dept):
    mgr = EmployeeManager()
    employees = mgr.list_all(status=status, department=dept)
    if not employees:
        console.print("[yellow]No employees found[/yellow]")
        return
    table = Table(title=f"Employees ({status})")
    table.add_column("ID", style="cyan")
    table.add_column("Code", style="green")
    table.add_column("Name")
    table.add_column("Department")
    table.add_column("Designation")
    table.add_column("Basic", justify="right")
    table.add_column("Status")
    for emp in employees:
        name = f"{emp['first_name']} {emp['last_name']}"
        table.add_row(
            str(emp["id"]), emp["employee_code"], name,
            emp["department"] or "-", emp["designation"] or "-",
            indian_format(emp["basic_pay"]), emp["status"],
        )
    console.print(table)


@employee.command(name="view")
@click.argument("identifier")
@db_context
def view_employee(identifier):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(identifier) if identifier.isdigit() else None) or \
          mgr.get(employee_code=identifier)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    table = Table(title=f"Employee: {emp['first_name']} {emp['last_name']}")
    fields = [
        ("ID", str(emp["id"])), ("Code", emp["employee_code"]),
        ("Name", f"{emp['first_name']} {emp['last_name']}"),
        ("DOB", emp["date_of_birth"] or "-"),
        ("Gender", emp["gender"] or "-"),
        ("PAN", emp["pan"] or "-"), ("UAN", emp["uan"] or "-"),
        ("ESI No", emp["esi_number"] or "-"),
        ("Bank", emp["bank_name"] or "-"),
        ("Account", emp["bank_account"] or "-"),
        ("IFSC", emp["ifsc_code"] or "-"),
        ("DOJ", emp["date_of_joining"]),
        ("DOR", emp["date_of_relieving"] or "-"),
        ("Department", emp["department"] or "-"),
        ("Designation", emp["designation"] or "-"),
        ("Location", emp["location"] or "-"),
        ("State", emp["state"] or "-"),
        ("Basic Pay", indian_format(emp["basic_pay"])),
        ("DA", indian_format(emp["da"])),
        ("HRA", indian_format(emp["hra"])),
        ("Conveyance", indian_format(emp["conveyance_allowance"])),
        ("Medical", indian_format(emp["medical_allowance"])),
        ("Special", indian_format(emp["special_allowance"])),
        ("Other", indian_format(emp["other_allowance"])),
        ("Tax Regime", emp["tax_regime"] or "old"),
        ("Status", emp["status"]),
    ]
    for label, value in fields:
        table.add_row(label, value)
    console.print(table)


@employee.command(name="update")
@click.argument("identifier")
@click.option("--first-name", help="First name")
@click.option("--last-name", help="Last name")
@click.option("--dept", help="Department")
@click.option("--designation", help="Designation")
@click.option("--basic", type=float, help="Basic pay")
@click.option("--da", type=float, help="Dearness Allowance")
@click.option("--hra", type=float, help="HRA")
@click.option("--pan", help="PAN number")
@click.option("--uan", help="UAN number")
@click.option("--bank", help="Bank name")
@click.option("--account", help="Bank account")
@click.option("--ifsc", help="IFSC code")
@click.option("--state", help="State for PT")
@click.option("--regime", type=click.Choice(["old", "new"]), help="Tax regime")
@click.option("--status", type=click.Choice(["active", "inactive"]), help="Status")
@click.option("--relieving-date", "--dor", help="Date of relieving (YYYY-MM-DD)")
@db_context
def update_employee(identifier, **kwargs):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(identifier) if identifier.isdigit() else None) or \
          mgr.get(employee_code=identifier)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    update_kwargs = {k.replace("-", "_"): v for k, v in kwargs.items() if v is not None}
    label_map = {"dept": "department", "bank": "bank_name", "account": "bank_account",
                 "ifsc": "ifsc_code", "state": "pt_state", "regime": "tax_regime",
                 "relieving_date": "date_of_relieving", "dor": "date_of_relieving"}
    for old, new in label_map.items():
        if old in update_kwargs:
            update_kwargs[new] = update_kwargs.pop(old)
    mgr.update(emp["id"], **update_kwargs)
    console.print("[green]Employee updated successfully[/green]")


@main.group()
def attendance():
    pass


@attendance.command(name="mark")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--date", "-d", required=True, help="Date (YYYY-MM-DD)")
@click.option("--status", "-s", required=True,
              type=click.Choice(["present", "absent", "half-day", "leave", "holiday", "weekoff"]),
              help="Attendance status")
@click.option("--in-time", help="In time (HH:MM)")
@click.option("--out-time", help="Out time (HH:MM)")
@click.option("--remarks", help="Remarks")
@db_context
def mark_attendance(employee, date, status, in_time, out_time, remarks):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    att = AttendanceManager()
    att.mark(emp["id"], date, status, in_time, out_time, remarks)
    console.print(f"[green]Attendance marked for {emp['first_name']} {emp['last_name']} on {date}[/green]")


@attendance.command(name="import")
@click.option("--file", "-f", required=True, help="Excel file path")
@click.option("--date-col", default="Date", help="Date column name")
@click.option("--emp-col", default="Employee Code", help="Employee code column")
@click.option("--status-col", default="Status", help="Status column")
@db_context
def import_attendance(file, date_col, emp_col, status_col):
    if not os.path.exists(file):
        console.print(f"[red]File not found: {file}[/red]")
        sys.exit(1)
    att = AttendanceManager()
    count = att.import_from_excel(file, date_col, emp_col, status_col)
    console.print(f"[green]Imported {count} attendance records[/green]")


@attendance.command(name="report")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def attendance_report(employee, month, year):
    if year is None:
        year = date.today().year
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    att = AttendanceManager()
    report = att.monthly_report(emp["id"], year, month)
    month_name = datetime(year, month, 1).strftime("%B")
    table = Table(title=f"Attendance Report: {emp['first_name']} {emp['last_name']} - {month_name} {year}")
    for key, value in report.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


@attendance.command(name="summary")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def attendance_summary(employee, year):
    if year is None:
        year = date.today().year
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    att = AttendanceManager()
    _, totals = att.summary(emp["id"], year)
    table = Table(title=f"Attendance Summary: {emp['first_name']} {emp['last_name']} - {year}")
    for key, value in totals.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


@main.group()
def leave():
    pass


@leave.command(name="apply")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--type", "-t", required=True, help="Leave type (EL/CL/SL/LWP)")
@click.option("--from", "-f", "from_date", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--to", "to_date", required=True, help="End date (YYYY-MM-DD)")
@click.option("--reason", "-r", help="Reason for leave")
@db_context
def apply_leave(employee, type, from_date, to_date, reason):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    lm = LeaveManager()
    leave_id, err = lm.apply(emp["id"], type.upper(), from_date, to_date, reason)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    console.print(f"[green]Leave applied. ID: {leave_id} (Pending approval)[/green]")


@leave.command(name="approve")
@click.option("--leave-id", "-l", required=True, type=int, help="Leave ID")
@click.option("--reject", "-r", is_flag=True, help="Reject instead of approve")
@click.option("--by", help="Approved by (name)")
@db_context
def approve_leave(leave_id, reject, by):
    lm = LeaveManager()
    if reject:
        success, err = lm.reject(leave_id, by)
    else:
        success, err = lm.approve(leave_id, by)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    action = "rejected" if reject else "approved"
    console.print(f"[green]Leave {leave_id} {action} successfully[/green]")


@leave.command(name="balance")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@db_context
def leave_balance(employee):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    lm = LeaveManager()
    fy = financial_year()
    balances = lm.get_balance(emp["id"], fy)
    table = Table(title=f"Leave Balance: {emp['first_name']} {emp['last_name']} - {fy}")
    table.add_column("Type")
    table.add_column("Opening")
    table.add_column("Credited")
    table.add_column("Used")
    table.add_column("Lapsed")
    table.add_column("Available")
    for lt, bal in balances.items():
        table.add_row(
            lt, str(bal["opening"]), str(bal["credited"]),
            str(bal["used"]), str(bal["lapsed"]), str(bal["available"]),
        )
    console.print(table)


@leave.command(name="report")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--fy", help="Financial year (e.g. 2024-2025)")
@db_context
def leave_report(employee, fy):
    if fy is None:
        fy = financial_year()
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    lm = LeaveManager()
    leaves, balances = lm.report(emp["id"], fy)
    table = Table(title=f"Leave Report: {emp['first_name']} {emp['last_name']} - {fy}")
    table.add_column("Type")
    table.add_column("Start")
    table.add_column("End")
    table.add_column("Days")
    table.add_column("Status")
    for lv in leaves:
        table.add_row(lv["leave_type"], lv["start_date"], lv["end_date"],
                      str(lv["total_days"]), lv["status"])
    console.print(table)


@main.group()
def payroll():
    pass


@payroll.command(name="process")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@click.option("--arrears", type=float, default=0, help="Arrears amount")
@click.option("--other-deductions", type=float, default=0, help="Other deductions")
@db_context
def process_payroll(employee, month, year, arrears, other_deductions):
    if year is None:
        year = date.today().year
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    pm = PayrollManager()
    payroll_id, err = pm.process(emp["id"], month, year, arrears, other_deductions)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    payroll = pm.get(emp["id"], month, year)
    console.print(f"[green]Payroll processed (ID: {payroll_id})[/green]")
    table = Table(title=f"Payroll: {emp['first_name']} {emp['last_name']}")
    table.add_column("Component")
    table.add_column("Amount", justify="right")
    items = [
        ("Gross Pay", payroll["gross_pay"]),
        ("PF (Employee)", payroll["pf_employee"]),
        ("ESI (Employee)", payroll["esi_employee"]),
        ("Professional Tax", payroll["pt"]),
        ("TDS", payroll["tds"]),
        ("Total Deductions", payroll["total_deductions"]),
        ("Net Pay", payroll["net_pay"]),
    ]
    for label, amount in items:
        table.add_row(label, indian_format(amount))
    console.print(table)


@payroll.command(name="slip")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@click.option("--output", "-o", help="Output PDF path")
@db_context
def salary_slip(employee, month, year, output):
    if year is None:
        year = date.today().year
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    pm = PayrollManager()
    path, err = pm.generate_salary_slip(emp["id"], month, year, output)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    console.print(f"[green]Salary slip generated: {path}[/green]")


@payroll.command(name="register")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@click.option("--dept", help="Filter by department")
@db_context
def payroll_register(month, year, dept):
    if year is None:
        year = date.today().year
    pm = PayrollManager()
    records = pm.register(month, year, dept)
    if not records:
        console.print("[yellow]No payroll records found[/yellow]")
        return
    table = Table(title=f"Payroll Register - {month}/{year}")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("Gross", justify="right")
    table.add_column("PF", justify="right")
    table.add_column("ESI", justify="right")
    table.add_column("PT", justify="right")
    table.add_column("TDS", justify="right")
    table.add_column("Net", justify="right")
    table.add_column("Status")
    for r in records:
        name = f"{r['first_name']} {r['last_name']}"
        table.add_row(
            r["employee_code"], name,
            indian_format(r["gross_pay"]), indian_format(r["pf_employee"]),
            indian_format(r["esi_employee"]), indian_format(r["pt"]),
            indian_format(r["tds"]), indian_format(r["net_pay"]),
            r["status"],
        )
    console.print(table)
    totals = {
        "gross": sum(r["gross_pay"] or 0 for r in records),
        "pf": sum(r["pf_employee"] or 0 for r in records),
        "esi": sum(r["esi_employee"] or 0 for r in records),
        "pt": sum(r["pt"] or 0 for r in records),
        "tds": sum(r["tds"] or 0 for r in records),
        "net": sum(r["net_pay"] or 0 for r in records),
    }
    console.print(f"\nTotals - Gross: {indian_format(totals['gross'])} | "
                  f"PF: {indian_format(totals['pf'])} | "
                  f"ESI: {indian_format(totals['esi'])} | "
                  f"PT: {indian_format(totals['pt'])} | "
                  f"TDS: {indian_format(totals['tds'])} | "
                  f"Net: {indian_format(totals['net'])}")


@payroll.command(name="arrears")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@click.option("--revised-basic", type=float, help="Revised basic pay")
@click.option("--revised-da", type=float, help="Revised DA")
@click.option("--revised-hra", type=float, help="Revised HRA")
@db_context
def arrears(employee, month, year, revised_basic, revised_da, revised_hra):
    if year is None:
        year = date.today().year
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    pm = PayrollManager()
    result, err = pm.arrears_calculation(
        emp["id"], month, year, revised_basic or emp["basic_pay"],
        revised_da or emp["da"], revised_hra or emp["hra"],
    )
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    console.print(f"Old Gross: {indian_format(result['old_gross'])}")
    console.print(f"Revised Gross: {indian_format(result['new_gross'])}")
    console.print(f"Arrears: [green]{indian_format(result['arrears'])}[/green]")


@main.group()
def statutory():
    pass


@statutory.command(name="pf")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def pf_report(month, year):
    if year is None:
        year = date.today().year
    sm = StatutoryManager()
    rows, totals = sm.pf_register(month, year)
    table = Table(title=f"PF Register - {month}/{year}")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("UAN")
    table.add_column("PF Wages", justify="right")
    table.add_column("EE Share", justify="right")
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        table.add_row(r["employee_code"], name, r["uan"] or "-",
                      indian_format(r["pf_employee"]),
                      indian_format(r["pf_employee"]))
    console.print(table)
    console.print(f"Total Employees: {totals['employee_count']} | "
                  f"Employee PF: {indian_format(totals['total_employee_pf'])}")


@statutory.command(name="esi")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def esi_report(month, year):
    if year is None:
        year = date.today().year
    sm = StatutoryManager()
    rows, totals = sm.esi_register(month, year)
    table = Table(title=f"ESI Register - {month}/{year}")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("ESI No")
    table.add_column("EE Share", justify="right")
    table.add_column("ER Share", justify="right")
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        table.add_row(r["employee_code"], name, r["esi_number"] or "-",
                      indian_format(r["esi_employee"]),
                      indian_format(r["esi_employer"]))
    console.print(table)
    console.print(f"Total: EE {indian_format(totals['total_employee_esi'])} | "
                  f"ER {indian_format(totals['total_employer_esi'])}")


@statutory.command(name="tds")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def tds_report(month, year):
    if year is None:
        year = date.today().year
    sm = StatutoryManager()
    rows, totals = sm.tds_register(month, year)
    table = Table(title=f"TDS Register - {month}/{year}")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("PAN")
    table.add_column("Regime")
    table.add_column("TDS", justify="right")
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        table.add_row(r["employee_code"], name, r["pan"] or "-",
                      r["tax_regime"] or "old", indian_format(r["tds"]))
    console.print(table)
    console.print(f"Total TDS: {indian_format(totals['total_tds'])}")


@statutory.command(name="pt")
@click.option("--month", "-m", type=int, required=True, help="Month (1-12)")
@click.option("--year", "-y", type=int, default=None, help="Year")
@db_context
def pt_report(month, year):
    if year is None:
        year = date.today().year
    sm = StatutoryManager()
    rows, totals = sm.pt_register(month, year)
    table = Table(title=f"Professional Tax Register - {month}/{year}")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("PT Amount", justify="right")
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        table.add_row(r["employee_code"], name, r["pt_state"] or "Karnataka",
                      indian_format(r["pt"]))
    console.print(table)
    console.print(f"Total PT: {indian_format(totals['total_pt'])}")


@main.group()
def settlement():
    pass


@settlement.command(name="calculate")
@click.option("--employee", "-e", required=True, help="Employee ID or code")
@click.option("--relieving-date", "-r", required=True, help="Date of relieving (YYYY-MM-DD)")
@click.option("--notice-days", type=int, default=0, help="Notice pay days")
@click.option("--other-payments", type=float, default=0, help="Other payments")
@click.option("--loan-deduction", type=float, default=0, help="Loan deduction")
@click.option("--other-deductions", type=float, default=0, help="Other deductions")
@click.option("--save", is_flag=True, help="Save to database")
@db_context
def calculate_settlement(employee, relieving_date, notice_days,
                         other_payments, loan_deduction, other_deductions, save):
    mgr = EmployeeManager()
    emp = mgr.get(employee_id=int(employee) if employee.isdigit() else None) or \
          mgr.get(employee_code=employee)
    if not emp:
        console.print("[red]Employee not found[/red]")
        sys.exit(1)
    sm = SettlementManager()
    result, err = sm.calculate(emp["id"], relieving_date, notice_days,
                                other_payments, loan_deduction, other_deductions)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    table = Table(title=f"Full & Final Settlement: {emp['first_name']} {emp['last_name']}")
    table.add_column("Component")
    table.add_column("Amount", justify="right")
    items = [
        ("Notice Pay", result["notice_pay_amount"]),
        ("Leave Encashment", result["leave_encashment_amount"]),
        ("Gratuity", result["gratuity_amount"]),
        ("Salary Due", result["salary_due_amount"]),
        ("Other Payments", result["other_payments"]),
        ("PF Settlement", result["pf_settlement"]),
        ("Loan Deduction", result["loan_deduction"]),
        ("Other Deductions", result["other_deductions"]),
        ("Net Settlement", result["net_settlement"]),
    ]
    for label, amount in items:
        table.add_row(label, indian_format(amount))
    console.print(table)
    if save:
        sid = sm.save(result)
        console.print(f"[green]Settlement saved with ID: {sid}[/green]")


@settlement.command(name="generate")
@click.option("--settlement-id", "-s", required=True, type=int, help="Settlement ID")
@click.option("--output", "-o", help="Output PDF path")
@db_context
def generate_letter(settlement_id, output):
    sm = SettlementManager()
    path, err = sm.generate_letter(settlement_id, output)
    if err:
        console.print(f"[red]{err}[/red]")
        sys.exit(1)
    console.print(f"[green]Settlement letter generated: {path}[/green]")


if __name__ == "__main__":
    main()
