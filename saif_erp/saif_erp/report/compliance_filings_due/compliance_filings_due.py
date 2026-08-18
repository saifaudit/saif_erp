# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Compliance Filings Due — open VAT / Corporate Tax filings by urgency (overdue -> red,
> 90 days -> green). Accountants see their own; management sees the firm."""

from collections import Counter

import frappe

from saif_erp.compliance import FILING_BANDS, get_open_filings

MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Partner", "Job Order Admin Support"}


def execute(filters=None):
	filters = filters or {}
	user = frappe.session.user
	if user != "Administrator" and not (MGMT_ROLES & set(frappe.get_roles(user))):
		rows = get_open_filings(accountant=user)  # accountant: own filings only
	else:
		rows = get_open_filings(accountant=filters.get("accountant"))

	if filters.get("service"):
		rows = [r for r in rows if r["service"] == filters.get("service")]
	if filters.get("band"):
		rows = [r for r in rows if r["band"] == filters.get("band")]
	if filters.get("company"):
		rows = [r for r in rows if r.get("company") == filters.get("company")]

	counts = Counter(r["band"] for r in rows)
	return _columns(), rows, None, _chart(counts), _summary(counts)


def _columns():
	return [
		{"label": "Client", "fieldname": "customer_name", "fieldtype": "Data", "width": 210},
		{"label": "Service", "fieldname": "service", "fieldtype": "Data", "width": 150},
		{"label": "Period", "fieldname": "period_label", "fieldtype": "Data", "width": 170},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{"label": "Days Left", "fieldname": "days_left", "fieldtype": "Int", "width": 90},
		{"label": "Status", "fieldname": "band", "fieldtype": "Data", "width": 120},
		{"label": "Filing", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Accountant", "fieldname": "accountant", "fieldtype": "Data", "width": 150},
		{"label": "Job Order", "fieldname": "job_order", "fieldtype": "Link", "options": "Job Order", "width": 140},
	]


def _chart(counts):
	labels = [b[0] for b in FILING_BANDS]
	return {
		"type": "bar",
		"data": {"labels": labels, "datasets": [{"name": "Filings", "values": [counts.get(b[0], 0) for b in FILING_BANDS]}]},
		"colors": ["#e0533d"],
	}


def _summary(counts):
	summary = [
		{"value": counts.get(label, 0), "label": label, "indicator": ind, "datatype": "Int"}
		for label, lo, hi, color, ind in FILING_BANDS
	]
	summary.append({"value": sum(counts.values()), "label": "Open filings", "indicator": "Grey", "datatype": "Int"})
	return summary
