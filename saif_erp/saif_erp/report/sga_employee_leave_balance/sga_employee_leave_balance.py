# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.from_date:
		filters.from_date = getdate(nowdate()).replace(month=1, day=1)
	if not filters.to_date:
		filters.to_date = nowdate()
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 200},
		{"label": _("Leave Type"), "fieldname": "leave_type", "fieldtype": "Link", "options": "Leave Type", "width": 200},
		{"label": _("Opening"), "fieldname": "opening", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": _("Allocated"), "fieldname": "allocated", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": _("Taken"), "fieldname": "taken", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": _("Expired"), "fieldname": "expired", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Float", "width": 100, "precision": 1},
	]


def get_data(filters):
	conditions = ["l.docstatus = 1"]
	params = {"from_date": filters.from_date, "to_date": filters.to_date}

	if filters.get("company"):
		conditions.append("e.company = %(company)s")
		params["company"] = filters.company
	if filters.get("employee"):
		conditions.append("l.employee = %(employee)s")
		params["employee"] = filters.employee
	if filters.get("leave_type"):
		conditions.append("l.leave_type = %(leave_type)s")
		params["leave_type"] = filters.leave_type
	if filters.get("employee_status"):
		conditions.append("e.status = %(employee_status)s")
		params["employee_status"] = filters.employee_status

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			l.employee,
			e.employee_name,
			e.company,
			l.leave_type,
			SUM(CASE WHEN l.from_date < %(from_date)s THEN l.leaves ELSE 0 END) AS opening,
			SUM(CASE WHEN l.transaction_type = 'Leave Allocation' AND l.is_expired = 0 AND l.leaves > 0
				AND l.from_date BETWEEN %(from_date)s AND %(to_date)s THEN l.leaves ELSE 0 END) AS allocated,
			-1 * SUM(CASE WHEN l.transaction_type = 'Leave Application'
				AND l.from_date BETWEEN %(from_date)s AND %(to_date)s THEN l.leaves ELSE 0 END) AS taken,
			-1 * SUM(CASE WHEN l.is_expired = 1
				AND l.from_date BETWEEN %(from_date)s AND %(to_date)s THEN l.leaves ELSE 0 END) AS expired,
			SUM(CASE WHEN l.from_date <= %(to_date)s THEN l.leaves ELSE 0 END) AS balance
		FROM `tabLeave Ledger Entry` l
		INNER JOIN `tabEmployee` e ON e.name = l.employee
		WHERE {where}
		GROUP BY l.employee, l.leave_type
		HAVING opening <> 0 OR allocated <> 0 OR taken <> 0 OR expired <> 0 OR balance <> 0
		ORDER BY e.employee_name, l.leave_type
		""",
		params,
		as_dict=True,
	)

	for r in rows:
		for k in ("opening", "allocated", "taken", "expired", "balance"):
			r[k] = flt(r[k], 1)
	return rows
