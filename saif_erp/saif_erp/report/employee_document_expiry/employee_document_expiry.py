# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Employee Document Expiry — passport / visa / Emirates ID / labour card / insurance
expiry, colour-coded by urgency (expired -> red, > 90 days -> green)."""

from collections import Counter

import frappe

from saif_erp.document_expiry import BANDS, get_expiring_documents

MGMT_ROLES = {"System Manager", "HR Manager", "HR User", "Job Order Admin",
              "Job Order Partner", "Job Order Admin Support"}


def execute(filters=None):
	filters = filters or {}
	user = frappe.session.user
	# HR / management see everyone (optionally by company); a regular employee sees
	# only their own documents.
	if user != "Administrator" and not (MGMT_ROLES & set(frappe.get_roles(user))):
		emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
		rows = get_expiring_documents(employee=emp, active_only=False) if emp else []
	else:
		rows = get_expiring_documents(company=filters.get("company"))

	if filters.get("document"):
		rows = [r for r in rows if r["document"] == filters.get("document")]
	if filters.get("band"):
		rows = [r for r in rows if r["band"] == filters.get("band")]
	if filters.get("only_expiring"):
		rows = [r for r in rows if r["days_left"] <= 90]

	counts = Counter(r["band"] for r in rows)
	return _columns(), rows, None, _chart(counts), _summary(counts)


def _columns():
	return [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": "Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Company", "fieldname": "company", "fieldtype": "Data", "width": 190},
		{"label": "Document", "fieldname": "document", "fieldtype": "Data", "width": 130},
		{"label": "Number", "fieldname": "number", "fieldtype": "Data", "width": 140},
		{"label": "Expiry Date", "fieldname": "expiry", "fieldtype": "Date", "width": 110},
		{"label": "Days Left", "fieldname": "days_left", "fieldtype": "Int", "width": 90},
		{"label": "Status", "fieldname": "band", "fieldtype": "Data", "width": 120},
	]


def _chart(counts):
	labels = [b[0] for b in BANDS]
	return {
		"type": "bar",
		"data": {"labels": labels, "datasets": [{"name": "Documents", "values": [counts.get(b[0], 0) for b in BANDS]}]},
		"colors": ["#e0533d"],
	}


def _summary(counts):
	summary = [
		{"value": counts.get(label, 0), "label": label, "indicator": ind, "datatype": "Int"}
		for label, lo, hi, color, ind in BANDS
	]
	summary.append({"value": sum(counts.values()), "label": "Total tracked",
	                "indicator": "Grey", "datatype": "Int"})
	return summary
