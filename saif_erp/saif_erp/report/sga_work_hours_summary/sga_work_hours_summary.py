# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Monthly work-hours summary per employee — how many hours each person actually
worked, and how many days fell SHORT of a full day (a proxy for late-in /
early-out). 'Short' is judged on working hours, not clock timing, so someone who
came early but worked a full day is not flagged. Managers see all (or one); staff
see only themselves."""

import calendar
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from saif_erp import api

MGMT_ROLES = {"System Manager", "HR Manager", "HR User",
              "Job Order Admin", "Job Order Partner"}
DEFAULT_FULL_DAY_HOURS = 9.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(nowdate())
	yr = cint(filters.year) or today.year
	mo = cint(filters.month) or today.month
	ndays = calendar.monthrange(yr, mo)[1]
	first, last = date(yr, mo, 1), date(yr, mo, ndays)
	full_day = flt(filters.min_hours) or DEFAULT_FULL_DAY_HOURS

	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))

	# A single employee → show the DAILY detail (which dates were short/late/early),
	# not the one-row summary. Managers reach it by clicking a row; staff always
	# see their own detail.
	target = filters.employee if (is_mgr and filters.get("employee")) else (
		None if is_mgr else frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name"))
	if target:
		return _detail(target, yr, mo, first, last, full_day)

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
	                           fields=["name", "employee_name", "company"], order_by="employee_name")
	if not employees:
		return get_columns(full_day), [], None, None, None

	agg = {r.employee: r for r in frappe.db.sql("""
		select employee,
			sum(case when working_hours > 0 then 1 else 0 end) worked_days,
			round(sum(coalesce(working_hours, 0)), 1) total_hours,
			sum(case when working_hours > 0 and working_hours < %(full)s then 1 else 0 end) short_days,
			round(sum(case when working_hours > 0 and working_hours < %(full)s
				then %(full)s - working_hours else 0 end), 1) short_hours,
			sum(coalesce(late_entry, 0)) late_flags,
			sum(coalesce(early_exit, 0)) early_flags
		from `tabAttendance`
		where attendance_date between %(first)s and %(last)s and docstatus = 1
			and employee in %(emps)s
		group by employee""",
		{"full": full_day, "first": first, "last": last,
		 "emps": tuple([e.name for e in employees])}, as_dict=True)}

	data, tot_short = [], 0
	for e in employees:
		a = agg.get(e.name)
		worked = (a.worked_days if a else 0) or 0
		total = (a.total_hours if a else 0) or 0
		short = (a.short_days if a else 0) or 0
		tot_short += short
		data.append({
			"employee": e.name, "employee_name": e.employee_name, "company": _short_company(e.company),
			"worked_days": worked, "total_hours": total,
			"avg_hours": round(total / worked, 1) if worked else 0,
			"full_days": worked - short, "short_days": short,
			"short_hours": (a.short_hours if a else 0) or 0,
			"late": (a.late_flags if a else 0) or 0, "early": (a.early_flags if a else 0) or 0,
		})

	summary = [
		{"label": _("Employees"), "value": len(data), "datatype": "Int", "indicator": "Green"},
		{"label": _("Short days (total)"), "value": tot_short, "datatype": "Int", "indicator": "Red"},
		{"label": _("Full-day = hours ≥"), "value": full_day, "datatype": "Float", "indicator": "Grey"},
	]
	return get_columns(full_day), data, _banner(yr, mo, filters, is_mgr, len(data), full_day), None, summary


def _detail(emp, yr, mo, first, last, full_day):
	"""Daily breakdown for one employee: each attendance day with In/Out, hours
	and a Short/Late/Early flag."""
	name = frappe.db.get_value("Employee", emp, "employee_name") or emp
	recs = frappe.db.sql(
		"""select attendance_date d, status, in_time, out_time,
			coalesce(working_hours, 0) wh, coalesce(late_entry, 0) le, coalesce(early_exit, 0) ee
		from `tabAttendance` where employee = %s and attendance_date between %s and %s and docstatus = 1
		order by attendance_date""", (emp, first, last), as_dict=True)
	data, n_short, n_late, n_early = [], 0, 0, 0
	for r in recs:
		flags = []
		if r.wh > 0 and r.wh < full_day:
			flags.append("Short"); n_short += 1
		if r.le:
			flags.append("Late"); n_late += 1
		if r.ee:
			flags.append("Early"); n_early += 1
		data.append({
			"date": r.d, "day": getdate(r.d).strftime("%a"), "status": r.status,
			"in_time": str(r.in_time)[11:16] if r.in_time else "",
			"out_time": str(r.out_time)[11:16] if r.out_time else "",
			"hours": round(flt(r.wh), 1), "flag": ", ".join(flags),
		})
	cols = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 95},
		{"label": _("Day"), "fieldname": "day", "fieldtype": "Data", "width": 55},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("In"), "fieldname": "in_time", "fieldtype": "Data", "width": 70},
		{"label": _("Out"), "fieldname": "out_time", "fieldtype": "Data", "width": 70},
		{"label": _("Hours"), "fieldname": "hours", "fieldtype": "Float", "width": 75, "precision": 1},
		{"label": _("Flag"), "fieldname": "flag", "fieldtype": "Data", "width": 160},
	]
	summary = [
		{"label": _("Short days"), "value": n_short, "datatype": "Int", "indicator": "Red"},
		{"label": _("Late in"), "value": n_late, "datatype": "Int", "indicator": "Orange"},
		{"label": _("Early out"), "value": n_early, "datatype": "Int", "indicator": "Orange"},
	]
	banner = (
		"<div style='padding:9px 14px;border-left:5px solid #3DB54A;background:#f3faf5;"
		"border-radius:6px;margin:2px 0 4px'>"
		"<span style='font-size:16px;font-weight:800;color:#155636'>Work Hours — Daily</span>"
		"<span style='color:#155636;font-weight:600;margin-left:8px'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s %s · a day under %g hrs is Short · "
		"clear the Employee filter to go back to all staff</span></div>"
		% (frappe.utils.escape_html(name), calendar.month_name[mo], yr, full_day))
	return cols, data, banner, None, summary


def _short_company(company):
	if not company:
		return ""
	return (company.replace("SGA World Auditing Accounting LLC", "SGA")
	        .replace("Saif Chartered Accountants LLC", "SAIF")
	        .replace("T K Chandy & Associates", "T K Chandy"))


def get_columns(full_day):
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Data", "width": 85},
		{"label": _("Worked Days"), "fieldname": "worked_days", "fieldtype": "Int", "width": 90},
		{"label": _("Total Hrs"), "fieldname": "total_hours", "fieldtype": "Float", "width": 85, "precision": 1},
		{"label": _("Avg Hrs/Day"), "fieldname": "avg_hours", "fieldtype": "Float", "width": 95, "precision": 1},
		{"label": _("Full Days"), "fieldname": "full_days", "fieldtype": "Int", "width": 80},
		{"label": _("Short Days"), "fieldname": "short_days", "fieldtype": "Int", "width": 85},
		{"label": _("Short Hrs"), "fieldname": "short_hours", "fieldtype": "Float", "width": 85, "precision": 1},
		{"label": _("Late In"), "fieldname": "late", "fieldtype": "Int", "width": 70},
		{"label": _("Early Out"), "fieldname": "early", "fieldtype": "Int", "width": 80},
	]


def _banner(yr, mo, filters, is_mgr, n, full_day):
	who = _("All Staff")
	emp = filters.get("employee") if is_mgr else None
	if not is_mgr:
		emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if emp:
		who = frappe.db.get_value("Employee", emp, "employee_name") or emp
	return (
		"<div style='padding:9px 14px;border-left:5px solid #3DB54A;background:#f3faf5;"
		"border-radius:6px;margin:2px 0 4px'>"
		"<span style='font-size:16px;font-weight:800;color:#155636'>Work Hours</span>"
		"<span style='color:#155636;font-weight:600;margin-left:8px'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s %s · %d staff · "
		"a day under %g hrs counts as SHORT · Late In / Early Out are the punch flags</span></div>"
		% (frappe.utils.escape_html(who), calendar.month_name[mo], yr, n, full_day)
	)
