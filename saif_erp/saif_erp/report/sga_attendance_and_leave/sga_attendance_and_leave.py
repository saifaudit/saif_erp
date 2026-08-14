# Copyright (c) 2026, SGA World FZ LLC and contributors
"""One easy-to-read row per employee: attendance for the selected month
(present / absent / on-leave / holidays / working days) alongside the leave
balance remaining in each leave type. Managers see everyone (or one, via the
Employee filter); other staff see only themselves."""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, nowdate

from saif_erp import api

MGMT_ROLES = {"System Manager", "HR Manager", "HR User",
              "Job Order Admin", "Job Order Partner"}

# leave type -> short column label; also fixes the column order
LEAVE_SHORT = [
	("Annual Leave", "Annual"),
	("Sick Leave (Medical Certificate)", "Sick"),
	("Casual Leave", "Casual"),
	("Earned Leave", "Earned"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	as_of = getdate(filters.date or nowdate())
	month = as_of.strftime("%Y-%m")
	yend = "%s-12-31" % as_of.year

	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))
	emp_filter = {"status": "Active"}
	if filters.get("company"):
		emp_filter["company"] = filters.company
	if is_mgr and filters.get("employee"):
		emp_filter["name"] = filters.employee
	if not is_mgr:  # staff locked to self
		self_emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		emp_filter = {"name": self_emp or "__none__"}

	employees = frappe.get_all(
		"Employee", filters=emp_filter, fields=["name", "employee_name", "company"],
		order_by="employee_name",
	)

	# which leave types to show as columns (those actually in use), in fixed order
	present = {r[0] for r in frappe.db.sql(
		"select distinct leave_type from `tabLeave Ledger Entry` where docstatus=1")}
	leave_cols = [(lt, short) for lt, short in LEAVE_SHORT if lt in present]

	# balances per (employee, leave type) as of the year end
	bal = {}
	for r in frappe.db.sql(
		"""select employee, leave_type, round(sum(leaves), 1) bal
		   from `tabLeave Ledger Entry`
		   where docstatus=1 and from_date <= %(yend)s and leave_type != 'Legacy Leave'
		   group by employee, leave_type""", {"yend": yend}, as_dict=True):
		bal[(r.employee, r.leave_type)] = r.bal

	data = []
	tot = {"Present": 0, "Absent": 0, "On Leave": 0}
	for e in employees:
		att = api._attendance_for(e.name, month)
		row = {
			"employee": e.name, "employee_name": e.employee_name,
			"company": _short_company(e.company),
			"present": att.get("Present", 0), "absent": att.get("Absent", 0),
			"on_leave": att.get("On Leave", 0), "holidays": att.get("holidays", 0),
			"working_days": att.get("working_days", 0),
		}
		for lt, short in leave_cols:
			row[short.lower()] = flt(bal.get((e.name, lt), 0), 1)
		row["legacy"] = flt(api._legacy_balance(e.name), 1)
		data.append(row)
		for k in tot:
			tot[k] += row["present" if k == "Present" else ("absent" if k == "Absent" else "on_leave")]

	columns = get_columns(leave_cols)
	summary = [
		{"label": _("Employees"), "value": len(data), "datatype": "Int", "indicator": "Green"},
		{"label": _("Present (total)"), "value": tot["Present"], "datatype": "Int", "indicator": "Green"},
		{"label": _("Absent (total)"), "value": tot["Absent"], "datatype": "Int", "indicator": "Red"},
		{"label": _("On leave (total)"), "value": tot["On Leave"], "datatype": "Int", "indicator": "Grey"},
	]
	return columns, data, _banner(as_of, filters, is_mgr, len(data)), None, summary


def _short_company(company):
	if not company:
		return ""
	# keep it readable in a narrow column
	return company.replace("SGA World Auditing Accounting LLC", "SGA").replace(
		"Saif Chartered Accountants LLC", "SAIF").replace("T K Chandy & Associates", "T K Chandy")


def get_columns(leave_cols):
	cols = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 175},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Data", "width": 90},
		{"label": _("Present"), "fieldname": "present", "fieldtype": "Int", "width": 75},
		{"label": _("Absent"), "fieldname": "absent", "fieldtype": "Int", "width": 75},
		{"label": _("On Leave"), "fieldname": "on_leave", "fieldtype": "Int", "width": 80},
		{"label": _("Holidays"), "fieldname": "holidays", "fieldtype": "Int", "width": 80},
		{"label": _("Working Days"), "fieldname": "working_days", "fieldtype": "Int", "width": 95},
	]
	for _lt, short in leave_cols:
		cols.append({"label": _(short), "fieldname": short.lower(), "fieldtype": "Float",
		             "width": 80, "precision": 1})
	cols.append({"label": _("Legacy"), "fieldname": "legacy", "fieldtype": "Float", "width": 80, "precision": 1})
	return cols


def _banner(as_of, filters, is_mgr, n):
	who = _("All Staff")
	emp = filters.get("employee") if is_mgr else None
	if not is_mgr:
		emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if emp:
		who = frappe.db.get_value("Employee", emp, "employee_name") or emp
	return (
		"<div style='padding:9px 14px;border-left:5px solid #3DB54A;background:#f3faf5;"
		"border-radius:6px;margin:2px 0 4px'>"
		"<span style='font-size:16px;font-weight:800;color:#155636'>Attendance &amp; Leave</span>"
		"<span style='color:#155636;font-weight:600;margin-left:8px'>%s</span>"
		"<span style='color:#777;margin-left:10px;font-size:12px'>%s · %d staff · leave balance as of %s</span></div>"
		% (frappe.utils.escape_html(who), as_of.strftime("%B %Y"), n, as_of.year)
	)
