# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""One consolidated monthly report per employee — merges the old
Monthly / Work Flow / Contributor reports. Includes the employee's OWNED
jobs and the jobs they CONTRIBUTE to (Role column), with workflow (status,
aging, carry-forward, collaborators) and money (proposed/invoiced/paid).

Scope: managers see everyone (or one, via the Employee filter); other staff
are always locked to their own jobs — so it serves both the admin and the
employee versions from a single report."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_first_day, getdate, nowdate

MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Admin Support",
              "Job Order Semi Admin", "Job Order Partner", "HR Manager"}
ACTIVE = ("Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending")
DONE = ("Finished", "Closed (Failed)")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.from_date:
		filters.from_date = get_first_day(nowdate())
	if not filters.to_date:
		filters.to_date = nowdate()
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Role"), "fieldname": "role", "fieldtype": "Data", "width": 95},
		{"label": _("Job Order"), "fieldname": "job_order", "fieldtype": "Link", "options": "Job Order", "width": 135},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 175},
		{"label": _("Service"), "fieldname": "service", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "job_status", "fieldtype": "Data", "width": 130},
		{"label": _("Job Date"), "fieldname": "job_date", "fieldtype": "Date", "width": 90},
		{"label": _("Aging"), "fieldname": "aging", "fieldtype": "Data", "width": 75},
		{"label": _("Carry Fwd"), "fieldname": "carry_forward", "fieldtype": "Data", "width": 80},
		{"label": _("Other Accountants"), "fieldname": "other_accountants", "fieldtype": "Data", "width": 175},
		{"label": _("Proposed"), "fieldname": "proposed_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Invoiced"), "fieldname": "invoiced_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Paid"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 100},
		{"label": _("Transfer"), "fieldname": "transfer", "fieldtype": "Data", "width": 140},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))
	users = None  # None = all (managers)
	if filters.get("employee"):
		uid = frappe.db.get_value("Employee", filters.employee, "user_id")
		users = [uid or "__none__"]
	if not is_mgr:
		users = [frappe.session.user]  # staff always locked to self

	params = {"from": filters.from_date, "to": filters.to_date, "active": ACTIVE}
	# new-this-period OR carried-forward-and-still-active
	period = "(jo.job_date between %(from)s and %(to)s or (jo.job_date < %(from)s and jo.job_status in %(active)s))"
	owned_u = contrib_u = ""
	if users is not None:
		params["users"] = tuple(users)
		owned_u = " and jo.accountant in %(users)s"
		contrib_u = " and joc.to_accountant in %(users)s"

	collab = "(select group_concat(distinct c2.to_accountant separator ', ') from `tabJob Order Contributors` c2 where c2.parent=jo.name)"
	sql = f"""
		select 'Accountant' role, jo.name job_order, jo.customer, coalesce(it.item_name, jo.service) service,
			jo.job_status, jo.job_date, jo.closure_date, jo.accountant emp_user,
			jo.proposed_amount, jo.invoiced_amount, jo.paid_amount, jo.job_status_remark remarks,
			jo.transferred_from, jo.transferred_to, {collab} other_accountants
		from `tabJob Order` jo left join `tabItem` it on it.name = jo.service
		where jo.docstatus=1 and {period}{owned_u}
		union all
		select 'Contributor', jo.name, jo.customer, coalesce(it.item_name, jo.service),
			jo.job_status, jo.job_date, jo.closure_date, joc.to_accountant,
			jo.proposed_amount, jo.invoiced_amount, jo.paid_amount, jo.job_status_remark,
			jo.transferred_from, jo.transferred_to, {collab}
		from `tabJob Order Contributors` joc
		join `tabJob Order` jo on jo.name = joc.parent
		left join `tabItem` it on it.name = jo.service
		where jo.docstatus=1 and {period}{contrib_u}
		order by job_date desc
	"""
	rows = frappe.db.sql(sql, params, as_dict=True)
	frm = getdate(filters.from_date)
	tdy = getdate(nowdate())
	out = []
	for r in rows:
		end = r.closure_date if (r.job_status in DONE and r.closure_date) else tdy
		aging = date_diff(end, r.job_date) if r.job_date else 0
		transfer = ""
		if r.transferred_to or r.transferred_from:
			transfer = ("%s → %s" % (r.transferred_from or "—", r.transferred_to or "—"))
		others = (r.other_accountants or "")
		if r.emp_user:
			others = ", ".join(a for a in others.split(", ") if a and a != r.emp_user)
		out.append({
			"role": r.role, "job_order": r.job_order, "customer": r.customer, "service": r.service,
			"job_status": r.job_status, "job_date": r.job_date,
			"aging": ("%d days" % aging) if aging is not None else "",
			"carry_forward": "Yes" if (r.job_date and getdate(r.job_date) < frm) else "No",
			"other_accountants": others,
			"proposed_amount": flt(r.proposed_amount), "invoiced_amount": flt(r.invoiced_amount),
			"paid_amount": flt(r.paid_amount), "transfer": transfer, "remarks": r.remarks,
		})
	return out
