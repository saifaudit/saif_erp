# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Payroll days summary — the attendance days that feed salary, per employee for
a month. Payable Days follows the ERPNext default: month days minus LOP (absent /
unpaid). Meant to be run for a COMPLETED month. Managers see all (or one); staff
see only themselves."""

import calendar

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from saif_erp import api

MGMT_ROLES = {"System Manager", "HR Manager", "HR User",
              "Job Order Admin", "Job Order Partner"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(nowdate())
	yr = cint(filters.year) or today.year
	mo = cint(filters.month) or today.month
	month = "%04d-%02d" % (yr, mo)
	total_days = calendar.monthrange(yr, mo)[1]

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
	                           fields=["name", "employee_name", "company"], order_by="employee_name")

	data = []
	tot_pay = tot_lop = 0
	for e in employees:
		att = api._attendance_for(e.name, month)
		# no half-days in use (management marks present/absent), so fold any into present
		present = att.get("Present", 0) + att.get("Work From Home", 0) + att.get("Half Day", 0)
		paid_leave = att.get("On Leave", 0)
		absent = att.get("Absent", 0)  # LOP
		payable = total_days - absent  # holidays + present + paid leave + unmarked are paid
		tot_pay += payable
		tot_lop += absent
		data.append({
			"employee": e.name, "employee_name": e.employee_name,
			"company": _short_company(e.company),
			"total_days": total_days, "holidays": att.get("holidays", 0),
			"working_days": att.get("working_days", 0),
			"present": present, "paid_leave": paid_leave,
			"lop": absent, "payable_days": payable,
		})

	summary = [
		{"label": _("Employees"), "value": len(data), "datatype": "Int", "indicator": "Green"},
		{"label": _("Payable days (total)"), "value": tot_pay, "datatype": "Int", "indicator": "Green"},
		{"label": _("LOP days (total)"), "value": tot_lop, "datatype": "Int", "indicator": "Red"},
	]
	return get_columns(), data, _banner(yr, mo, filters, is_mgr, len(data)), None, summary


def _short_company(company):
	if not company:
		return ""
	return (company.replace("SGA World Auditing Accounting LLC", "SGA")
	        .replace("Saif Chartered Accountants LLC", "SAIF")
	        .replace("T K Chandy & Associates", "T K Chandy"))


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 175},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Data", "width": 90},
		{"label": _("Total Days"), "fieldname": "total_days", "fieldtype": "Int", "width": 85},
		{"label": _("Holidays"), "fieldname": "holidays", "fieldtype": "Int", "width": 80},
		{"label": _("Working Days"), "fieldname": "working_days", "fieldtype": "Int", "width": 95},
		{"label": _("Present"), "fieldname": "present", "fieldtype": "Int", "width": 80},
		{"label": _("Paid Leave"), "fieldname": "paid_leave", "fieldtype": "Int", "width": 85},
		{"label": _("LOP"), "fieldname": "lop", "fieldtype": "Int", "width": 70},
		{"label": _("Payable Days"), "fieldname": "payable_days", "fieldtype": "Int", "width": 100},
	]


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
		"<span style='font-size:16px;font-weight:800;color:#155636'>Payroll Days</span>"
		"<span style='color:#155636;font-weight:600;margin-left:8px'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s %s · %d staff · "
		"Payable = month days − LOP</span></div>"
		% (frappe.utils.escape_html(who), calendar.month_name[mo], yr, n)
	)
