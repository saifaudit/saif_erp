# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Job Order Aging — active job orders bucketed by days since job_date, with a
colour-coded summary (green -> red). Accountants see only their own; managers and
Admin Support see the firm (optionally filtered by company / accountant)."""

import frappe
from collections import Counter

# (label, min_days, max_days_or_None, hex_colour, frappe_indicator)
BUCKETS = [
	("≤ 10 days", 0, 10, "#22a06b", "Green"),
	("11 – 20 days", 11, 20, "#4a9de0", "Blue"),
	("21 – 30 days", 21, 30, "#7c6ee6", "Blue"),
	("31 – 45 days", 31, 45, "#e6a817", "Orange"),
	("46 – 90 days", 46, 90, "#e8804d", "Orange"),
	("91 – 180 days", 91, 180, "#e0533d", "Red"),
	("181 – 365 days", 181, 365, "#c1272d", "Red"),
	("365+ days", 366, None, "#8b1a1a", "Red"),
]

MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Partner",
              "Job Order Semi Admin", "Job Order Admin Support"}


def _bucket(age):
	for label, lo, hi, _c, _i in BUCKETS:
		if hi is None:
			if age >= lo:
				return label
		elif lo <= age <= hi:
			return label
	return BUCKETS[0][0]


def _is_manager():
	u = frappe.session.user
	return u == "Administrator" or bool(MGMT_ROLES & set(frappe.get_roles(u)))


def execute(filters=None):
	filters = filters or {}
	where, params = [], {}

	# Accountants are locked to their own job orders; managers may filter.
	if not _is_manager():
		where.append("jo.accountant = %(me)s")
		params["me"] = frappe.session.user
	elif filters.get("accountant"):
		where.append("jo.accountant = %(accountant)s")
		params["accountant"] = filters.get("accountant")
	if filters.get("company"):
		where.append("jo.company = %(company)s")
		params["company"] = filters.get("company")

	cond = (" and " + " and ".join(where)) if where else ""
	rows = frappe.db.sql(
		f"""select jo.name, jo.customer, jo.company, jo.service, jo.accountant,
			jo.job_status, jo.job_date, datediff(curdate(), jo.job_date) as age_days
		from `tabJob Order` jo
		where jo.docstatus < 2 and jo.job_status not in ('Finished','Closed (Failed)')
			and jo.job_date is not null{cond}
		order by age_days desc""",
		params, as_dict=True,
	)
	for r in rows:
		r["bucket"] = _bucket(r["age_days"])

	counts = Counter(r["bucket"] for r in rows)

	bfilter = filters.get("bucket")
	data = [r for r in rows if not bfilter or r["bucket"] == bfilter]

	return _columns(), data, None, _chart(counts), _summary(counts)


def _columns():
	return [
		{"label": "Job Order", "fieldname": "name", "fieldtype": "Link", "options": "Job Order", "width": 150},
		{"label": "Client", "fieldname": "customer", "fieldtype": "Data", "width": 200},
		{"label": "Company", "fieldname": "company", "fieldtype": "Data", "width": 180},
		{"label": "Service", "fieldname": "service", "fieldtype": "Data", "width": 190},
		{"label": "Accountant", "fieldname": "accountant", "fieldtype": "Data", "width": 150},
		{"label": "Status", "fieldname": "job_status", "fieldtype": "Data", "width": 120},
		{"label": "Job Date", "fieldname": "job_date", "fieldtype": "Date", "width": 100},
		{"label": "Age (days)", "fieldname": "age_days", "fieldtype": "Int", "width": 100},
		{"label": "Aging Bucket", "fieldname": "bucket", "fieldtype": "Data", "width": 130},
	]


def _chart(counts):
	labels = [b[0] for b in BUCKETS]
	values = [counts.get(b[0], 0) for b in BUCKETS]
	return {
		"type": "bar",
		"data": {"labels": labels, "datasets": [{"name": "Active job orders", "values": values}]},
		"colors": ["#e0533d"],
		"barOptions": {"stacked": 0},
		"axisOptions": {"xIsSeries": 0},
	}


def _summary(counts):
	summary = [
		{"value": counts.get(label, 0), "label": label, "indicator": ind, "datatype": "Int"}
		for label, lo, hi, color, ind in BUCKETS
	]
	summary.append({"value": sum(counts.values()), "label": "Total active",
	                "indicator": "Grey", "datatype": "Int"})
	return summary
