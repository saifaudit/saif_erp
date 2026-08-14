# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Day-by-day monthly attendance sheet (one row per employee, one column per day)
for preparing WPS / payroll. Each cell marks the day: P present, A absent,
L on leave, W work-from-home, ½ half day, S weekly-off (Sat/Sun), H holiday.
Managers see all (or one); staff see only themselves."""

import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from saif_erp import api

MGMT_ROLES = {"System Manager", "HR Manager", "HR User",
              "Job Order Admin", "Job Order Partner"}

# No half-days in use — management marks a half day as Present or Absent (with a
# remark), so "Half Day" (if it ever appears) is treated as Present.
STATUS_CODE = {"Present": "P", "Absent": "A", "On Leave": "L",
               "Work From Home": "W", "Half Day": "P"}
WEEKDAY = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
           "Friday": 4, "Saturday": 5, "Sunday": 6}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(nowdate())
	yr = cint(filters.year) or today.year
	mo = cint(filters.month) or today.month
	ndays = calendar.monthrange(yr, mo)[1]
	first, last = date(yr, mo, 1), date(yr, mo, ndays)

	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))
	emp_filter = {"status": "Active"}
	if filters.get("company"):
		emp_filter["company"] = filters.company
	if is_mgr and filters.get("employee"):
		emp_filter["name"] = filters.employee
	if not is_mgr:
		self_emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		emp_filter = {"name": self_emp or "__none__"}
	if "name" not in emp_filter:  # all-staff list → drop management
		ex = api.hr_report_exclude_names()
		if ex:
			emp_filter["name"] = ["not in", ex]
	employees = frappe.get_all("Employee", filters=emp_filter,
	                           fields=["name", "employee_name", "holiday_list"], order_by="employee_name")

	data = []
	for e in employees:
		att = {getdate(r.attendance_date): r.status for r in frappe.db.sql(
			"select attendance_date, status from `tabAttendance` where employee=%s "
			"and attendance_date between %s and %s and docstatus=1", (e.name, first, last), as_dict=True)}
		wo_idx, holidays = None, set()
		if e.holiday_list:
			wo = frappe.db.get_value("Holiday List", e.holiday_list, "weekly_off")
			wo_idx = WEEKDAY.get(wo)
			holidays = {getdate(r[0]) for r in frappe.db.sql(
				"select holiday_date from `tabHoliday` where parent=%s and holiday_date between %s and %s",
				(e.holiday_list, first, last))}

		row = {"employee": e.name, "employee_name": e.employee_name}
		cnt = {"P": 0, "A": 0, "L": 0, "W": 0, "off": 0}
		for d in range(1, ndays + 1):
			dt = date(yr, mo, d)
			status = att.get(dt)
			if dt in holidays:
				code = "H"  # public holiday
			elif wo_idx is not None and dt.weekday() == wo_idx:
				code = "S"  # weekly off (Sunday)
			elif dt.weekday() == 5:  # Saturday = work-from-home by policy
				code = {"Absent": "A", "On Leave": "L"}.get(status, "W")
			elif status:
				code = STATUS_CODE.get(status, "")  # Mon–Fri: use the marked status
			else:
				code = ""  # working day, no attendance record
			row["d%d" % d] = code
			if code == "P":
				cnt["P"] += 1
			elif code == "W":
				cnt["W"] += 1
			elif code == "A":
				cnt["A"] += 1
			elif code == "L":
				cnt["L"] += 1
			elif code in ("S", "H"):
				cnt["off"] += 1
		row.update({"t_present": cnt["P"], "t_absent": cnt["A"], "t_leave": cnt["L"],
		            "t_wfh": cnt["W"], "t_off": cnt["off"]})
		data.append(row)

	return get_columns(yr, mo, ndays), data, _banner(yr, mo, filters, is_mgr, len(data)), None, None


def get_columns(yr, mo, ndays):
	cols = [{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 165}]
	for d in range(1, ndays + 1):
		wd = date(yr, mo, d).strftime("%a")[:2]  # Mo Tu We ...
		cols.append({"label": "%d\n%s" % (d, wd), "fieldname": "d%d" % d,
		             "fieldtype": "Data", "width": 34, "align": "center"})
	cols += [
		{"label": _("P"), "fieldname": "t_present", "fieldtype": "Int", "width": 45},
		{"label": _("A"), "fieldname": "t_absent", "fieldtype": "Int", "width": 45},
		{"label": _("L"), "fieldname": "t_leave", "fieldtype": "Int", "width": 45},
		{"label": _("WFH"), "fieldname": "t_wfh", "fieldtype": "Int", "width": 50},
		{"label": _("Off"), "fieldname": "t_off", "fieldtype": "Int", "width": 45},
	]
	return cols


def _banner(yr, mo, filters, is_mgr, n):
	who = _("All Staff")
	emp = filters.get("employee") if is_mgr else None
	if not is_mgr:
		emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if emp:
		who = frappe.db.get_value("Employee", emp, "employee_name") or emp
	return (
		"<div style='padding:9px 14px;border-left:5px solid #3DB54A;background:#f3faf5;"
		"border-radius:6px;margin:2px 0 4px'>"
		"<span style='font-size:16px;font-weight:800;color:#155636'>Monthly Attendance Sheet</span>"
		"<span style='color:#155636;font-weight:600;margin-left:8px'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s %s · %d staff · "
		"P present · A absent · L leave · W home · S week-off · H holiday</span></div>"
		% (frappe.utils.escape_html(who), calendar.month_name[mo], yr, n)
	)
