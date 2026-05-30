import sqlite3
from datetime import datetime, date, timedelta
from calendar import monthrange
import os
from fpdf import FPDF
from . import utils


class EmployeeManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def add(self, employee_code, first_name, last_name, date_of_joining, **kwargs):
        fields = {
            "employee_code": employee_code,
            "first_name": first_name,
            "last_name": last_name,
            "date_of_joining": date_of_joining,
        }
        for k, v in kwargs.items():
            if v is not None:
                fields[k] = v
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        values = tuple(fields.values())
        try:
            cur = self.conn.execute(
                f"INSERT INTO employees ({cols}) VALUES ({placeholders})", values
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get(self, employee_id=None, employee_code=None):
        if employee_id:
            cur = self.conn.execute(
                "SELECT * FROM employees WHERE id = ?", (employee_id,)
            )
        elif employee_code:
            cur = self.conn.execute(
                "SELECT * FROM employees WHERE employee_code = ?", (employee_code,)
            )
        else:
            return None
        return cur.fetchone()

    def list_all(self, status="active", department=None):
        query = "SELECT * FROM employees WHERE status = ?"
        params = [status]
        if department:
            query += " AND department = ?"
            params.append(department)
        query += " ORDER BY employee_code"
        return self.conn.execute(query, params).fetchall()

    def update(self, employee_id, **kwargs):
        allowed = [
            "first_name", "last_name", "date_of_birth", "gender", "pan", "uan",
            "esi_number", "bank_name", "bank_account", "ifsc_code",
            "date_of_relieving", "department", "designation", "location", "state",
            "basic_pay", "da", "hra", "conveyance_allowance", "medical_allowance",
            "special_allowance", "other_allowance", "pf_number", "pt_state",
            "tax_regime", "status",
        ]
        updates = {}
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                updates[k] = v
        if not updates:
            return False
        updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = tuple(updates.values()) + (employee_id,)
        self.conn.execute(
            f"UPDATE employees SET {set_clause} WHERE id = ?", values
        )
        self.conn.commit()
        return True

    def delete(self, employee_id):
        self.conn.execute("UPDATE employees SET status = 'inactive' WHERE id = ?", (employee_id,))
        self.conn.commit()
        return True


class AttendanceManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def mark(self, employee_id, att_date, status, in_time=None, out_time=None, remarks=None):
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO attendance
                   (employee_id, date, status, in_time, out_time, remarks)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (employee_id, att_date, status, in_time, out_time, remarks),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def bulk_mark(self, records):
        for rec in records:
            self.mark(**rec)
        return True

    def import_from_excel(self, filepath, date_col, employee_col, status_col, date_format="%Y-%m-%d"):
        import pandas as pd
        df = pd.read_excel(filepath)
        count = 0
        for _, row in df.iterrows():
            emp_code = row[employee_col]
            emp = self.conn.execute(
                "SELECT id FROM employees WHERE employee_code = ?", (str(emp_code),)
            ).fetchone()
            if not emp:
                continue
            att_date = datetime.strptime(str(row[date_col]), date_format).strftime("%Y-%m-%d")
            status_raw = str(row[status_col]).strip().lower()
            status_map = {
                "present": "present", "p": "present", "1": "present", "yes": "present",
                "absent": "absent", "a": "absent", "0": "absent", "no": "absent",
                "half-day": "half-day", "half day": "half-day", "hd": "half-day",
                "leave": "leave", "l": "leave", "on leave": "leave",
                "holiday": "holiday", "h": "holiday",
                "weekoff": "weekoff", "wo": "weekoff", "week off": "weekoff",
            }
            status = status_map.get(status_raw, "absent")
            self.mark(emp["id"], att_date, status)
            count += 1
        return count

    def get_attendance(self, employee_id, year, month):
        start, end = utils.month_boundaries(year, month)
        rows = self.conn.execute(
            """SELECT date, status FROM attendance
               WHERE employee_id = ? AND date >= ? AND date <= ?
               ORDER BY date""",
            (employee_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return {r["date"]: r["status"] for r in rows}

    def monthly_report(self, employee_id, year, month):
        total_days = utils.days_in_month(year, month)
        attendance = self.get_attendance(employee_id, year, month)
        present = sum(1 for s in attendance.values() if s == "present")
        absent = sum(1 for s in attendance.values() if s == "absent")
        half_days = sum(1 for s in attendance.values() if s == "half-day")
        leaves = sum(1 for s in attendance.values() if s == "leave")
        holidays = sum(1 for s in attendance.values() if s == "holiday")
        weekoffs = sum(1 for s in attendance.values() if s == "weekoff")
        unmarked = total_days - len(attendance)
        return {
            "total_days": total_days,
            "marked_days": len(attendance),
            "present": present,
            "absent": absent,
            "half_days": half_days,
            "leaves": leaves,
            "holidays": holidays,
            "weekoffs": weekoffs,
            "unmarked": unmarked,
            "paid_days": present + half_days * 0.5 + holidays + leaves,
        }

    def summary(self, employee_id, year):
        summary = {}
        for m in range(1, 13):
            rep = self.monthly_report(employee_id, year, m)
            summary[m] = rep
        totals = {
            "present": sum(s["present"] for s in summary.values()),
            "absent": sum(s["absent"] for s in summary.values()),
            "leaves": sum(s["leaves"] for s in summary.values()),
            "half_days": sum(s["half_days"] for s in summary.values()),
            "holidays": sum(s["holidays"] for s in summary.values()),
            "weekoffs": sum(s["weekoffs"] for s in summary.values()),
        }
        return summary, totals


class LeaveManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def get_leave_types(self):
        return self.conn.execute("SELECT * FROM leave_types").fetchall()

    def get_balance(self, employee_id, fy=None):
        if fy is None:
            fy = utils.financial_year()
        rows = self.conn.execute(
            """SELECT leave_type, opening, credited, used, lapsed
               FROM leave_balance
               WHERE employee_id = ? AND financial_year = ?""",
            (employee_id, fy),
        ).fetchall()
        if not rows:
            self._init_balance(employee_id, fy)
            rows = self.conn.execute(
                """SELECT leave_type, opening, credited, used, lapsed
                   FROM leave_balance
                   WHERE employee_id = ? AND financial_year = ?""",
                (employee_id, fy),
            ).fetchall()
        balances = {}
        for r in rows:
            available = r["opening"] + r["credited"] - r["used"] - r["lapsed"]
            balances[r["leave_type"]] = {
                "opening": r["opening"],
                "credited": r["credited"],
                "used": r["used"],
                "lapsed": r["lapsed"],
                "available": max(0, available),
            }
        return balances

    def _init_balance(self, employee_id, fy):
        types = self.get_leave_types()
        for lt in types:
            if lt["code"] == "LWP":
                continue
            self.conn.execute(
                """INSERT OR IGNORE INTO leave_balance
                   (employee_id, financial_year, leave_type, opening, credited)
                   VALUES (?, ?, ?, ?, ?)""",
                (employee_id, fy, lt["code"], 0, lt["days_per_year"]),
            )
        self.conn.commit()

    def credit_yearly(self, employee_id, fy=None):
        if fy is None:
            fy = utils.financial_year()
        types = self.get_leave_types()
        for lt in types:
            if lt["code"] == "LWP":
                continue
            bal = self.conn.execute(
                """SELECT opening, credited, used, lapsed FROM leave_balance
                   WHERE employee_id = ? AND financial_year = ? AND leave_type = ?""",
                (employee_id, fy, lt["code"]),
            ).fetchone()
            if bal:
                unused = bal["opening"] + bal["credited"] - bal["used"]
                cf = min(unused, lt["carry_forward"])
                lapse = unused - cf
                self.conn.execute(
                    """UPDATE leave_balance
                       SET lapsed = ?, opening = ?
                       WHERE employee_id = ? AND financial_year = ? AND leave_type = ?""",
                    (lapse, cf, employee_id, fy, lt["code"]),
                )
            else:
                self.conn.execute(
                    """INSERT INTO leave_balance
                       (employee_id, financial_year, leave_type, opening, credited)
                       VALUES (?, ?, ?, ?, ?)""",
                    (employee_id, fy, lt["code"], 0, lt["days_per_year"]),
                )
        self.conn.commit()

    def _count_working_days(self, employee_id, start_date, end_date):
        current = start_date
        count = 0.0
        while current <= end_date:
            att = self.conn.execute(
                "SELECT status FROM attendance WHERE employee_id = ? AND date = ?",
                (employee_id, current.isoformat()),
            ).fetchone()
            if att and att["status"] in ("holiday", "weekoff"):
                current += timedelta(days=1)
                continue
            count += 1.0
            current += timedelta(days=1)
        return count

    def apply(self, employee_id, leave_type, start_date, end_date, reason=None):
        s = datetime.strptime(start_date, "%Y-%m-%d").date()
        e = datetime.strptime(end_date, "%Y-%m-%d").date()
        total_days = self._count_working_days(employee_id, s, e)
        if total_days <= 0:
            return None, "No working days in selected range"
        if leave_type != "LWP":
            fy = utils.financial_year()
            bal = self.get_balance(employee_id, fy)
            if leave_type not in bal or bal[leave_type]["available"] < total_days:
                return None, f"Insufficient {leave_type} balance"
        cur = self.conn.execute(
            """INSERT INTO leaves (employee_id, leave_type, start_date, end_date, total_days, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (employee_id, leave_type, start_date, end_date, total_days, reason),
        )
        self.conn.commit()
        return cur.lastrowid, None

    def approve(self, leave_id, approved_by=None):
        leave = self.conn.execute(
            "SELECT * FROM leaves WHERE id = ?", (leave_id,)
        ).fetchone()
        if not leave:
            return False, "Leave not found"
        if leave["status"] != "pending":
            return False, f"Leave is already {leave['status']}"
        self.conn.execute(
            """UPDATE leaves SET status = 'approved', approved_by = ?,
               approved_on = datetime('now','localtime') WHERE id = ?""",
            (approved_by, leave_id),
        )
        fy = utils.financial_year(
            datetime.strptime(leave["start_date"], "%Y-%m-%d").date()
        )
        self.conn.execute(
            """UPDATE leave_balance SET used = used + ?
               WHERE employee_id = ? AND financial_year = ? AND leave_type = ?""",
            (leave["total_days"], leave["employee_id"], fy, leave["leave_type"]),
        )
        emp_id = leave["employee_id"]
        s = datetime.strptime(leave["start_date"], "%Y-%m-%d").date()
        e = datetime.strptime(leave["end_date"], "%Y-%m-%d").date()
        current = s
        while current <= e:
            self.conn.execute(
                """INSERT OR REPLACE INTO attendance (employee_id, date, status, remarks)
                   VALUES (?, ?, 'leave', ?)""",
                (emp_id, current.isoformat(), f"{leave['leave_type']} leave"),
            )
            current += timedelta(days=1)
        self.conn.commit()
        return True, None

    def reject(self, leave_id, approved_by=None):
        leave = self.conn.execute(
            "SELECT * FROM leaves WHERE id = ?", (leave_id,)
        ).fetchone()
        if not leave:
            return False, "Leave not found"
        if leave["status"] != "pending":
            return False, f"Leave is already {leave['status']}"
        self.conn.execute(
            """UPDATE leaves SET status = 'rejected', approved_by = ?,
               approved_on = datetime('now','localtime') WHERE id = ?""",
            (approved_by, leave_id),
        )
        self.conn.commit()
        return True, None

    def pending_leaves(self, employee_id=None):
        if employee_id:
            return self.conn.execute(
                """SELECT l.*, e.first_name, e.last_name, e.employee_code
                   FROM leaves l JOIN employees e ON l.employee_id = e.id
                   WHERE l.status = 'pending' AND l.employee_id = ?
                   ORDER BY l.start_date""",
                (employee_id,),
            ).fetchall()
        return self.conn.execute(
            """SELECT l.*, e.first_name, e.last_name, e.employee_code
               FROM leaves l JOIN employees e ON l.employee_id = e.id
               WHERE l.status = 'pending'
               ORDER BY l.start_date"""
        ).fetchall()

    def report(self, employee_id, fy=None):
        if fy is None:
            fy = utils.financial_year()
        fy_start, fy_end = utils.financial_year_range(fy)
        leaves = self.conn.execute(
            """SELECT * FROM leaves
               WHERE employee_id = ? AND start_date >= ? AND end_date <= ?
               ORDER BY start_date""",
            (employee_id, fy_start.isoformat(), fy_end.isoformat()),
        ).fetchall()
        balances = self.get_balance(employee_id, fy)
        return leaves, balances


class PayrollManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def process(self, employee_id, month, year, arrears=0, other_deductions=0):
        emp = self.conn.execute(
            "SELECT * FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        if not emp:
            return None, "Employee not found"

        total_days = utils.days_in_month(year, month)
        att_mgr = AttendanceManager(self.conn)
        report = att_mgr.monthly_report(employee_id, year, month)
        paid_days = report["paid_days"]

        basic = emp["basic_pay"] or 0
        da = emp["da"] or 0
        hra = emp["hra"] or 0
        conv = emp["conveyance_allowance"] or 0
        medical = emp["medical_allowance"] or 0
        special = emp["special_allowance"] or 0
        other = emp["other_allowance"] or 0

        if paid_days < total_days:
            factor = paid_days / total_days
            basic = round(basic * factor, 2)
            da = round(da * factor, 2)
            hra = round(hra * factor, 2)
            conv = round(conv * factor, 2)
            medical = round(medical * factor, 2)
            special = round(special * factor, 2)
            other = round(other * factor, 2)

        gross_pay = round(basic + da + hra + conv + medical + special + other, 2)
        pf_wages = basic + da

        pf = utils.calculate_pf(basic, da) if pf_wages > 0 else {
            "employee": 0, "employer_epf": 0, "employer_eps": 0,
            "employer_edlis": 0, "employer_total": 0,
        }

        esi = utils.calculate_esi(gross_pay)

        pt = utils.get_pt(gross_pay, emp["pt_state"] or "Karnataka")

        yearly_projected = gross_pay * 12
        tds = utils.monthly_tds(
            yearly_projected, regime=emp["tax_regime"] or "old"
        )

        leave_deduction = 0
        if paid_days < total_days:
            lwp_leaves = self.conn.execute(
                """SELECT COALESCE(SUM(total_days), 0) FROM leaves
                   WHERE employee_id = ? AND leave_type = 'LWP'
                   AND status = 'approved'
                   AND strftime('%m', start_date) = ? AND strftime('%Y', start_date) = ?""",
                (employee_id, f"{month:02d}", str(year)),
            ).fetchone()[0]
            if lwp_leaves:
                daily_rate = ((emp["basic_pay"] or 0) + (emp["da"] or 0)) / 30
                leave_deduction = round(daily_rate * lwp_leaves, 2)

        total_deductions = round(
            pf["employee"] + esi["employee"] + pt + tds + leave_deduction + other_deductions,
            2,
        )
        net_pay = round(gross_pay - total_deductions + arrears, 2)
        employer_total = round(
            pf["employer_total"] + esi["employer"], 2
        )
        ctc = round(gross_pay + employer_total, 2)

        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO payroll
                   (employee_id, month, year, basic_pay, da, hra,
                    conveyance_allowance, medical_allowance, special_allowance,
                    other_allowance, gross_pay,
                    pf_employee, pf_employer, esi_employee, esi_employer,
                    pt, tds, leave_deduction, arrears, other_deductions,
                    total_deductions, net_pay, total_days, paid_days,
                    employer_contribution, ctc, status, processed_on)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           'processed', datetime('now','localtime'))""",
                (
                    employee_id, month, year,
                    basic, da, hra, conv, medical, special, other, gross_pay,
                    pf["employee"], pf["employer_total"],
                    esi["employee"], esi["employer"],
                    pt, tds, leave_deduction, arrears, other_deductions,
                    total_deductions, net_pay, total_days, paid_days,
                    employer_total, ctc,
                ),
            )
            self.conn.commit()
            payroll_id = self.conn.execute(
                "SELECT id FROM payroll WHERE employee_id = ? AND month = ? AND year = ?",
                (employee_id, month, year),
            ).fetchone()[0]
            return payroll_id, None
        except sqlite3.IntegrityError as e:
            return None, f"Payroll already exists: {e}"

    def get(self, employee_id, month, year):
        return self.conn.execute(
            """SELECT p.*, e.first_name, e.last_name, e.employee_code,
                      e.department, e.designation, e.pan, e.uan, e.pf_number,
                      e.bank_name, e.bank_account, e.ifsc_code
               FROM payroll p JOIN employees e ON p.employee_id = e.id
               WHERE p.employee_id = ? AND p.month = ? AND p.year = ?""",
            (employee_id, month, year),
        ).fetchone()

    def register(self, month, year, department=None):
        query = """SELECT p.*, e.first_name, e.last_name, e.employee_code,
                          e.department, e.designation, e.pan, e.uan
                   FROM payroll p JOIN employees e ON p.employee_id = e.id
                   WHERE p.month = ? AND p.year = ?"""
        params = [month, year]
        if department:
            query += " AND e.department = ?"
            params.append(department)
        query += " ORDER BY e.employee_code"
        return self.conn.execute(query, params).fetchall()

    def generate_salary_slip(self, employee_id, month, year, output_path=None):
        payroll = self.get(employee_id, month, year)
        if not payroll:
            return None, "Payroll record not found"
        if output_path is None:
            output_dir = os.path.join(os.path.expanduser("~"), ".atulya_hr", "slips")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir,
                f"SalarySlip_{payroll['employee_code']}_{year}{month:02d}.pdf",
            )
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(190, 10, "SALARY SLIP", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 10)
        month_name = datetime(year, month, 1).strftime("%B")
        pdf.cell(190, 6, f"Period: {month_name} {year}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(190, 7, "Employee Details", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        details = [
            (f"Employee Code: {payroll['employee_code']}", f"Name: {payroll['first_name']} {payroll['last_name']}"),
            (f"Department: {payroll['department'] or '-'}", f"Designation: {payroll['designation'] or '-'}"),
            (f"PAN: {payroll['pan'] or '-'}", f"UAN: {payroll['uan'] or '-'}"),
            (f"Bank: {payroll['bank_name'] or '-'}", f"Account: {payroll['bank_account'] or '-'}"),
            (f"Paid Days: {payroll['paid_days']}/{payroll['total_days']}", f"PF No: {payroll['pf_number'] or '-'}"),
        ]
        for left, right in details:
            pdf.cell(95, 5, left)
            pdf.cell(95, 5, right, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(190, 7, "Earnings", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        earnings = [
            ("Basic Pay", payroll["basic_pay"]),
            ("Dearness Allowance", payroll["da"]),
            ("House Rent Allowance", payroll["hra"]),
            ("Conveyance Allowance", payroll["conveyance_allowance"]),
            ("Medical Allowance", payroll["medical_allowance"]),
            ("Special Allowance", payroll["special_allowance"]),
            ("Other Allowance", payroll["other_allowance"]),
            ("Arrears", payroll["arrears"]),
        ]
        for label, amount in earnings:
            if amount and amount > 0:
                pdf.cell(140, 5, label)
                pdf.cell(50, 5, utils.indian_format(amount), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(140, 6, "Gross Pay", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(50, 6, utils.indian_format(payroll["gross_pay"]), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(190, 7, "Deductions", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        deductions = [
            ("Employee PF (12%)", payroll["pf_employee"]),
            ("Employee ESI (0.75%)", payroll["esi_employee"]),
            ("Professional Tax", payroll["pt"]),
            ("TDS/Income Tax", payroll["tds"]),
            ("Leave Deduction", payroll["leave_deduction"]),
            ("Other Deductions", payroll["other_deductions"]),
        ]
        for label, amount in deductions:
            if amount and amount > 0:
                pdf.cell(140, 5, label)
                pdf.cell(50, 5, utils.indian_format(amount), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(140, 6, "Total Deductions", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(50, 6, utils.indian_format(payroll["total_deductions"]), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(140, 8, "NET PAY (in hand)")
        pdf.cell(50, 8, f"Rs. {utils.indian_format(payroll['net_pay'])}", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

        pdf.set_font("Helvetica", "", 8)
        pdf.cell(190, 5, "Employer Contributions:", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(190, 5, f"PF: {utils.indian_format(payroll['pf_employer'])} | ESI: {utils.indian_format(payroll['esi_employer'])} | CTC: {utils.indian_format(payroll['ctc'])}", new_x="LMARGIN", new_y="NEXT")

        pdf.output(output_path)
        return output_path, None

    def arrears_calculation(self, employee_id, month, year,
                            revised_basic=None, revised_da=None, revised_hra=None,
                            revised_conv=None, revised_medical=None,
                            revised_special=None, revised_other=None):
        payroll = self.get(employee_id, month, year)
        if not payroll:
            return None, "Payroll record not found"
        old_gross = payroll["gross_pay"]
        new_gross = (
            (revised_basic or payroll["basic_pay"]) +
            (revised_da or payroll["da"]) +
            (revised_hra or payroll["hra"]) +
            (revised_conv or payroll["conveyance_allowance"]) +
            (revised_medical or payroll["medical_allowance"]) +
            (revised_special or payroll["special_allowance"]) +
            (revised_other or payroll["other_allowance"])
        )
        arrears = round(new_gross - old_gross, 2)
        if arrears < 0:
            arrears = 0
        return {"old_gross": old_gross, "new_gross": new_gross, "arrears": arrears}, None


class StatutoryManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def pf_register(self, month, year):
        rows = self.conn.execute(
            """SELECT p.*, e.employee_code, e.first_name, e.last_name, e.uan, e.pf_number,
                      e.basic_pay as emp_basic, e.da as emp_da
               FROM payroll p JOIN employees e ON p.employee_id = e.id
               WHERE p.month = ? AND p.year = ? AND (p.pf_employee > 0 OR p.pf_employer > 0)
               ORDER BY e.employee_code""",
            (month, year),
        ).fetchall()
        totals = {
            "employee_count": len(rows),
            "total_pf_wages": 0,
            "total_employee_pf": 0,
            "total_employer_epf": 0,
            "total_employer_eps": 0,
            "total_employer_edlis": 0,
        }
        for r in rows:
            pf_wages = utils.get_pf_wages(r["emp_basic"] or 0, r["emp_da"] or 0)
            totals["total_pf_wages"] += pf_wages
            totals["total_employee_pf"] += r["pf_employee"] or 0
        return rows, totals

    def esi_register(self, month, year):
        rows = self.conn.execute(
            """SELECT p.*, e.employee_code, e.first_name, e.last_name,
                      e.esi_number
               FROM payroll p JOIN employees e ON p.employee_id = e.id
               WHERE p.month = ? AND p.year = ? AND (p.esi_employee > 0 OR p.esi_employer > 0)
               ORDER BY e.employee_code""",
            (month, year),
        ).fetchall()
        totals = {
            "employee_count": len(rows),
            "total_employee_esi": sum(r["esi_employee"] or 0 for r in rows),
            "total_employer_esi": sum(r["esi_employer"] or 0 for r in rows),
        }
        return rows, totals

    def tds_register(self, month, year):
        rows = self.conn.execute(
            """SELECT p.*, e.employee_code, e.first_name, e.last_name,
                      e.pan, e.tax_regime
               FROM payroll p JOIN employees e ON p.employee_id = e.id
               WHERE p.month = ? AND p.year = ? AND p.tds > 0
               ORDER BY e.employee_code""",
            (month, year),
        ).fetchall()
        totals = {
            "employee_count": len(rows),
            "total_tds": sum(r["tds"] or 0 for r in rows),
        }
        return rows, totals

    def pt_register(self, month, year):
        rows = self.conn.execute(
            """SELECT p.*, e.employee_code, e.first_name, e.last_name,
                      e.pt_state
               FROM payroll p JOIN employees e ON p.employee_id = e.id
               WHERE p.month = ? AND p.year = ? AND p.pt > 0
               ORDER BY e.employee_code""",
            (month, year),
        ).fetchall()
        totals = {
            "employee_count": len(rows),
            "total_pt": sum(r["pt"] or 0 for r in rows),
        }
        return rows, totals


class SettlementManager:
    def __init__(self, conn=None):
        self.conn = conn or utils.get_connection()

    def calculate(self, employee_id, relieving_date, notice_pay_days=0,
                  other_payments=0, loan_deduction=0, other_deductions=0):
        emp = self.conn.execute(
            "SELECT * FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        if not emp:
            return None, "Employee not found"

        doj = datetime.strptime(emp["date_of_joining"], "%Y-%m-%d").date()
        rel = datetime.strptime(relieving_date, "%Y-%m-%d").date()
        years_of_service = max(0, (rel - doj).days // 365)

        basic = emp["basic_pay"] or 0
        da = emp["da"] or 0
        hra = emp["hra"] or 0

        notice_pay = utils.calculate_notice_pay(basic, da, hra, notice_pay_days)

        fy = utils.financial_year(rel)
        leave_mgr = LeaveManager(self.conn)
        balances = leave_mgr.get_balance(employee_id, fy)
        unused_el = balances.get("EL", {}).get("available", 0) if balances else 0
        leave_encash = utils.calculate_leave_encashment(basic, da, unused_el)

        gratuity = utils.calculate_gratuity(basic, da, years_of_service)

        last_payroll = self.conn.execute(
            """SELECT * FROM payroll WHERE employee_id = ?
               ORDER BY year DESC, month DESC LIMIT 1""",
            (employee_id,),
        ).fetchone()
        salary_due = last_payroll["net_pay"] if last_payroll else 0

        pf_balance = 0
        pf_rows = self.conn.execute(
            "SELECT pf_employee FROM payroll WHERE employee_id = ?", (employee_id,)
        ).fetchall()
        if pf_rows:
            pf_balance = sum(r["pf_employee"] or 0 for r in pf_rows)

        net = round(
            notice_pay + leave_encash + gratuity + salary_due +
            other_payments - pf_balance - loan_deduction - other_deductions,
            2,
        )

        settlement_data = {
            "employee_id": employee_id,
            "relieving_date": relieving_date,
            "notice_pay_days": notice_pay_days,
            "notice_pay_amount": notice_pay,
            "leave_encashment_days": unused_el,
            "leave_encashment_amount": leave_encash,
            "gratuity_years": years_of_service,
            "gratuity_amount": gratuity,
            "salary_due_amount": salary_due,
            "other_payments": other_payments,
            "pf_settlement": pf_balance,
            "loan_deduction": loan_deduction,
            "other_deductions": other_deductions,
            "net_settlement": net,
        }
        return settlement_data, None

    def save(self, settlement_data):
        cols = ", ".join(settlement_data.keys())
        placeholders = ", ".join("?" for _ in settlement_data)
        values = tuple(settlement_data.values())
        cur = self.conn.execute(
            f"INSERT INTO settlements ({cols}) VALUES ({placeholders})", values
        )
        self.conn.commit()
        return cur.lastrowid

    def get(self, settlement_id):
        return self.conn.execute(
            "SELECT * FROM settlements WHERE id = ?", (settlement_id,)
        ).fetchone()

    def generate_letter(self, settlement_id, output_path=None):
        settlement = self.conn.execute(
            """SELECT s.*, e.first_name, e.last_name, e.employee_code,
                      e.department, e.designation, e.date_of_joining,
                      e.basic_pay, e.da, e.hra
               FROM settlements s JOIN employees e ON s.employee_id = e.id
               WHERE s.id = ?""",
            (settlement_id,),
        ).fetchone()
        if not settlement:
            return None, "Settlement not found"

        if output_path is None:
            output_dir = os.path.join(os.path.expanduser("~"), ".atulya_hr", "settlements")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(
                output_dir,
                f"FullFinal_{settlement['employee_code']}_{settlement['id']}.pdf",
            )

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(190, 10, "FULL AND FINAL SETTLEMENT", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(190, 10, "SETTLEMENT LETTER", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(190, 7, "Employee Details", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        details = [
            (f"Name: {settlement['first_name']} {settlement['last_name']}", f"Code: {settlement['employee_code']}"),
            (f"Department: {settlement['department'] or '-'}", f"Designation: {settlement['designation'] or '-'}"),
            (f"Date of Joining: {settlement['date_of_joining']}", f"Date of Relieving: {settlement['relieving_date']}"),
        ]
        for left, right in details:
            pdf.cell(95, 6, left)
            pdf.cell(95, 6, right, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(190, 7, "Settlement Breakdown", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        items = [
            ("Notice Pay", settlement["notice_pay_amount"]),
            ("Leave Encashment", settlement["leave_encashment_amount"]),
            ("Gratuity", settlement["gratuity_amount"]),
            ("Salary Due", settlement["salary_due_amount"]),
            ("Other Payments", settlement["other_payments"]),
        ]
        for label, amount in items:
            if amount and amount > 0:
                pdf.cell(140, 6, label)
                pdf.cell(50, 6, utils.indian_format(amount), align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(140, 6, "Gross Settlement")
        pdf.cell(50, 6, utils.indian_format(sum(v for _, v in items)), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 9)
        deductions = [
            ("PF Settlement / Advance", settlement["pf_settlement"]),
            ("Loan Deduction", settlement["loan_deduction"]),
            ("Other Deductions", settlement["other_deductions"]),
        ]
        for label, amount in deductions:
            if amount and amount > 0:
                pdf.cell(140, 6, label)
                pdf.cell(50, 6, utils.indian_format(amount), align="R", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(140, 8, "NET SETTLEMENT AMOUNT")
        pdf.cell(50, 8, f"Rs. {utils.indian_format(settlement['net_settlement'])}", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(20)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(190, 6, "This is a computer-generated settlement letter.", new_x="LMARGIN", new_y="NEXT")
        pdf.output(output_path)
        return output_path, None
