# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""One consolidated monthly report per employee — merges the old
Monthly / Work Flow / Contributor reports. Includes the employee's OWNED
jobs and the jobs they CONTRIBUTE to (Role column), with workflow (status,
aging, carry-forward, collaborators) and money (proposed/invoiced/paid).

Scope: managers see everyone (or one, via the Employee filter); other staff
are always locked to their own jobs — so it serves both the admin and the
employee versions from a single report."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_first_day, getdate, nowdate

MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Admin Support",
              "Job Order Semi Admin", "Job Order Partner", "HR Manager"}
ACTIVE = ("Open", "Progress", "Under Review", "Awaiting Client Data", "Temporarily stopped", "Pending")
DONE = ("Finished", "Closed (Failed)")
# "on hold" jobs stall for client/external reasons, not employee performance —
# excluded from the turnaround/efficiency time so staff aren't penalised for them.
HOLD = ("Temporarily stopped", "Awaiting Client Data")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.from_date:
		filters.from_date = get_first_day(nowdate())
	if not filters.to_date:
		filters.to_date = nowdate()
	data, summary, chart = get_data(filters)
	return get_columns(), data, None, chart, summary


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


def _finish_dates(names):
	"""Best-effort finish date per job from the change-log (track_changes): the
	timestamp it last moved into a DONE status. Used only where the manual
	Closure Date is blank (which is ~93% of finished jobs). Historical/migrated
	jobs with no change-log simply have no finish date and are left out of the
	turnaround average rather than guessed."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select docname, creation, data from `tabVersion`
		   where ref_doctype='Job Order' and docname in %(n)s
		     and data like '%%job_status%%' order by creation asc""",
		{"n": tuple(names)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		try:
			d = json.loads(r.data)
		except Exception:
			continue
		for ch in d.get("changed", []):
			if ch and ch[0] == "job_status" and ch[2] in DONE:
				out[r.docname] = getdate(r.creation)  # asc order → last DONE wins
	return out


def get_data(filters):
	is_mgr = bool(MGMT_ROLES & set(frappe.get_roles()))
	users = None  # None = all (managers)
	if filters.get("employee"):
		uid = frappe.db.get_value("Employee", filters.employee, "user_id")
		users = [uid or "__none__"]
	if not is_mgr:
		users = [frappe.session.user]  # staff always locked to self

	params = {"from": filters.from_date, "to": filters.to_date, "active": ACTIVE}
	# new-this-period OR carried-forward-and-still-active OR carried-and-closed-this-period
	period = ("(jo.job_date between %(from)s and %(to)s"
	          " or (jo.job_date < %(from)s and jo.job_status in %(active)s)"
	          " or (jo.job_date < %(from)s and jo.closure_date between %(from)s and %(to)s))")
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
	to = getdate(filters.to_date)
	tdy = getdate(nowdate())
	finish_log = _finish_dates(list({r.job_order for r in rows}))
	out, turnaround = [], []  # turnaround = finished jobs with a known finish date
	for r in rows:
		fin = r.closure_date or finish_log.get(r.job_order)
		fin = getdate(fin) if fin else None
		is_done = r.job_status in DONE
		on_hold = r.job_status in HOLD
		end = fin if (is_done and fin) else tdy
		aging = date_diff(end, r.job_date) if r.job_date else 0
		if is_done and fin and r.job_date and frm <= fin <= to:
			turnaround.append(date_diff(fin, r.job_date))
		transfer = ""
		if r.transferred_to or r.transferred_from:
			transfer = ("%s → %s" % (r.transferred_from or "—", r.transferred_to or "—"))
		others = (r.other_accountants or "")
		if r.emp_user:
			others = ", ".join(a for a in others.split(", ") if a and a != r.emp_user)
		out.append({
			"role": r.role, "job_order": r.job_order, "customer": r.customer, "service": r.service,
			"job_status": r.job_status, "job_date": r.job_date,
			"aging": ("%d days" % aging),
			"carry_forward": "Yes" if (r.job_date and getdate(r.job_date) < frm) else "No",
			"other_accountants": others,
			"proposed_amount": flt(r.proposed_amount), "invoiced_amount": flt(r.invoiced_amount),
			"paid_amount": flt(r.paid_amount), "transfer": transfer, "remarks": r.remarks,
			"_finish": fin, "_done": is_done, "_hold": on_hold,
		})

	# ---- efficiency summary (headline numbers) ----
	# Money is split into THIS-PERIOD jobs vs CARRIED-FORWARD jobs so the
	# headline figures reflect only the selected month, not value that may
	# have been invoiced/earned in earlier months on still-open jobs.
	this_rows = [d for d in out if d["carry_forward"] == "No"]
	carr_rows = [d for d in out if d["carry_forward"] == "Yes"]
	this_month = len(this_rows)
	carried = len(carr_rows)
	single = sum(1 for d in out if not d["other_accountants"] and d["role"] == "Accountant")
	collab = sum(1 for d in out if d["other_accountants"] or d["role"] == "Contributor")
	# Finished THIS PERIOD = jobs whose finish date falls inside the window
	# (not merely "currently Finished"), so it measures output for the month.
	finished_period = sum(1 for d in out if d["_done"] and d["_finish"] and frm <= d["_finish"] <= to)
	on_hold = sum(1 for d in out if d["_hold"])
	# fair turnaround: finished jobs with a known finish date only — excludes
	# still-open and on-hold jobs, so client-side delays don't inflate it.
	avg_turn = round(sum(turnaround) / len(turnaround)) if turnaround else "—"
	inv_new = sum(d["invoiced_amount"] for d in this_rows)
	col_new = sum(d["paid_amount"] for d in this_rows)
	inv_carr = sum(d["invoiced_amount"] for d in carr_rows)
	col_carr = sum(d["paid_amount"] for d in carr_rows)
	summary = [
		{"label": _("Works handled"), "value": len(out), "datatype": "Int", "indicator": "Blue"},
		{"label": _("New this month"), "value": this_month, "datatype": "Int", "indicator": "Blue"},
		{"label": _("Carried forward"), "value": carried, "datatype": "Int", "indicator": "Orange"},
		{"label": _("Single work"), "value": single, "datatype": "Int"},
		{"label": _("Collaborated"), "value": collab, "datatype": "Int", "indicator": "Purple"},
		{"label": _("Finished this month"), "value": finished_period, "datatype": "Int", "indicator": "Green"},
		{"label": _("On hold (client)"), "value": on_hold, "datatype": "Int", "indicator": "Red"},
		{"label": _("Avg turnaround (finished, days)"), "value": avg_turn,
		 "datatype": "Int" if turnaround else "Data"},
		{"label": _("Invoiced (this month)"), "value": inv_new, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Collected (this month)"), "value": col_new, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Invoiced (carried fwd)"), "value": inv_carr, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Collected (carried fwd)"), "value": col_carr, "datatype": "Currency", "indicator": "Orange"},
	]

	# ---- chart: workload by status ----
	from collections import Counter
	sc = Counter(d["job_status"] for d in out)
	chart = {
		"type": "donut",
		"data": {"labels": list(sc.keys()), "datasets": [{"name": "Jobs", "values": list(sc.values())}]},
		"height": 260,
	}
	return out, summary, chart
