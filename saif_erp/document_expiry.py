# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Shared employee-document expiry logic used by the report, the dashboard card,
and the 30-day reminder email. Documents tracked: Passport (standard fields) plus
the UAE custom fields added by setup_document_expiry_fields."""

import frappe

# (label, number_field, expiry_field)
DOCS = [
	("Passport", "passport_number", "valid_upto"),
	("Residence Visa", "custom_visa_number", "custom_visa_expiry"),
	("Emirates ID", "custom_emirates_id", "custom_emirates_id_expiry"),
	("Labour Card", "custom_labour_card_no", "custom_labour_card_expiry"),
	("Health Insurance", "custom_insurance_policy", "custom_insurance_expiry"),
]

# (label, min_days, max_days, hex_colour, frappe_indicator) — min/max None = open-ended
BANDS = [
	("Expired", None, -1, "#8b1a1a", "Red"),
	("≤ 30 days", 0, 30, "#e0533d", "Red"),
	("31 – 60 days", 31, 60, "#e8804d", "Orange"),
	("61 – 90 days", 61, 90, "#e6a817", "Orange"),
	("> 90 days", 91, None, "#22a06b", "Green"),
]


def band(days):
	for label, lo, hi, color, ind in BANDS:
		if lo is None:
			if days <= hi:
				return label, color, ind
		elif hi is None:
			if days >= lo:
				return label, color, ind
		elif lo <= days <= hi:
			return label, color, ind
	return BANDS[-1][0], BANDS[-1][3], BANDS[-1][4]


def get_expiring_documents(company=None, within_days=None, active_only=True):
	"""One dict per (employee, document) that has an expiry date set, sorted soonest
	first. within_days limits to documents at/under that many days to expiry."""
	filt = {}
	if active_only:
		filt["status"] = "Active"
	if company:
		filt["company"] = company
	fields = ["name", "employee_name", "company", "user_id"]
	for _l, numf, expf in DOCS:
		fields += [numf, expf]
	today = frappe.utils.getdate(frappe.utils.today())
	out = []
	for e in frappe.get_all("Employee", filters=filt, fields=fields):
		for label, numf, expf in DOCS:
			exp = e.get(expf)
			if not exp:
				continue
			days = (frappe.utils.getdate(exp) - today).days
			if within_days is not None and days > within_days:
				continue
			b, color, ind = band(days)
			out.append({
				"employee": e.name, "employee_name": e.employee_name, "company": e.company,
				"user_id": e.get("user_id"), "document": label, "number": e.get(numf),
				"expiry": exp, "days_left": days, "band": b, "_color": color, "indicator": ind,
			})
	out.sort(key=lambda r: r["days_left"])
	return out
