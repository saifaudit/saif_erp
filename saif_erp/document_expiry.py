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


def get_expiring_documents(company=None, within_days=None, active_only=True, employee=None):
	"""One dict per (employee, document) that has an expiry date set, sorted soonest
	first. within_days limits to documents at/under that many days to expiry;
	employee limits to a single Employee (used for the per-employee self alert)."""
	filt = {}
	if active_only:
		filt["status"] = "Active"
	if company:
		filt["company"] = company
	if employee:
		filt["name"] = employee
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


def _hr_recipients():
	"""HR/admin who should be copied on expiry reminders. Override via site_config
	`saif_doc_expiry_recipients` (list); otherwise HR Manager users, else the admin."""
	cfg = frappe.conf.get("saif_doc_expiry_recipients")
	if cfg:
		return cfg if isinstance(cfg, list) else [cfg]
	users = frappe.get_all("Has Role", {"role": "HR Manager", "parenttype": "User"}, pluck="parent")
	users = [u for u in users if "@" in u and u not in ("Administrator", "Guest")]
	return users or ["santhosh@saifaudit.com"]


def notify_document_expiry():
	"""Daily reminder: email HR + the affected employee ahead of each document's
	expiry (30 and 7 days by default; override via `saif_doc_expiry_reminder_days`).
	Dormant on the local bench (scheduler + email off); fires on production."""
	reminder_days = frappe.conf.get("saif_doc_expiry_reminder_days") or [30, 7]
	hr = _hr_recipients()
	for d in get_expiring_documents(within_days=max(reminder_days)):
		if d["days_left"] not in reminder_days:
			continue
		recipients = list(hr)
		if d.get("user_id") and "@" in d["user_id"] and d["user_id"] not in recipients:
			recipients.append(d["user_id"])
		if not recipients:
			continue
		subject = "Document expiry: {doc} for {name} in {n} days".format(
			doc=d["document"], name=d["employee_name"], n=d["days_left"])
		message = frappe.render_template(
			"""<p>Reminder — the following employee document is due for renewal.</p>
			<table cellpadding="6" style="border-collapse:collapse">
			<tr><td><b>Employee</b></td><td>{{ name }}</td></tr>
			<tr><td><b>Company</b></td><td>{{ company }}</td></tr>
			<tr><td><b>Document</b></td><td>{{ doc }}</td></tr>
			<tr><td><b>Number</b></td><td>{{ number or "&mdash;" }}</td></tr>
			<tr><td><b>Expiry date</b></td><td>{{ expiry }}</td></tr>
			<tr><td><b>Days remaining</b></td><td style="color:#c1272d"><b>{{ n }}</b></td></tr>
			</table>
			<p>Please arrange the renewal before the expiry date.</p>""",
			{"name": d["employee_name"], "company": d.get("company") or "-",
			 "doc": d["document"], "number": d.get("number"),
			 "expiry": frappe.utils.formatdate(d["expiry"]), "n": d["days_left"]},
		)
		frappe.sendmail(recipients=recipients, subject=subject, message=message,
		                reference_doctype="Employee", reference_name=d["employee"])
