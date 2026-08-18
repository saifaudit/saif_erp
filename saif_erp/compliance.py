# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Compliance Register logic — statutory filing deadlines (VAT / Corporate Tax) driven
off Job Orders. One register per Customer + Service; each filing period tracks its due
date, status and the Job Order/accountant handling it. See docstrings per function."""

import datetime
import re

import frappe
from frappe.utils import add_days, add_months, get_last_day, getdate, today

# service -> filing rule. due = (unit, n) added to the period-end date.
SERVICE_RULES = {
	"Corporate Tax Return": {"frequency": "Annual", "due": ("months", 9)},
	"VAT Returns": {"frequency": "Quarterly", "due": ("days", 28)},
}

# how many days before the due date to start reminding
REMINDER_DAYS = [30, 15, 7]
OPEN_STATUSES = ("Pending", "Job Created")


def compute_due_date(service, period_end):
	rule = SERVICE_RULES.get(service)
	if not (rule and period_end):
		return None
	pe = getdate(period_end)
	unit, n = rule["due"]
	return add_months(pe, n) if unit == "months" else add_days(pe, n)


def parse_period_end(text):
	"""Best-effort: pull a period-END date out of the free-text Job Order period.
	Handles 'X to Y', 'year ended <date>', 'Month DD, YYYY', 'DD/MM/YYYY', 'Month YYYY',
	and bare 'YYYY'. Returns a date or None."""
	if not text:
		return None
	t = str(text).strip()
	if re.search(r"\bto\b", t, flags=re.I):
		t = re.split(r"\s+to\s+", t, flags=re.I)[-1].strip()
	m = re.search(r"end(?:ed|ing)?\s+(.*)$", t, flags=re.I)
	if m:
		t = m.group(1).strip()
	t = t.strip().rstrip(".")
	for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%d %B %Y", "%Y-%m-%d"):
		try:
			return datetime.datetime.strptime(t, fmt).date()
		except ValueError:
			pass
	m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", t)  # "Month YYYY" -> end of that month
	if m:
		try:
			d = datetime.datetime.strptime(f"01 {m.group(1)} {m.group(2)}", "%d %B %Y").date()
			return getdate(get_last_day(d))
		except ValueError:
			pass
	if re.match(r"^\d{4}$", t):  # bare year -> 31 Dec
		return datetime.date(int(t), 12, 31)
	return None


def get_or_create_register(customer, service, company=None):
	name = frappe.db.exists("Compliance Register", {"customer": customer, "service": service})
	if name:
		return frappe.get_doc("Compliance Register", name)
	reg = frappe.get_doc({
		"doctype": "Compliance Register", "customer": customer, "service": service,
		"frequency": SERVICE_RULES.get(service, {}).get("frequency", "Annual"),
		"active": 1, "company": company,
	})
	reg.insert(ignore_permissions=True)
	return reg


def sync_job_order(doc, method=None):
	"""doc_event on Job Order: if it's a tracked filing (VAT/CT) with a period-end date,
	link it into the customer's Compliance Register — creating/updating the matching
	period, its accountant and status (Filed once the Job Order is Finished)."""
	service = doc.get("service")
	if service not in SERVICE_RULES:
		return
	period_end = doc.get("custom_period_end_date") or parse_period_end(doc.get("period"))
	if not (doc.get("customer") and period_end):
		return

	reg = get_or_create_register(doc.customer, service, doc.get("company"))
	row = next((p for p in reg.periods if str(getdate(p.period_end_date)) == str(getdate(period_end))), None)
	if not row:
		row = reg.append("periods", {"period_end_date": getdate(period_end),
		                             "period_label": doc.get("period") or str(getdate(period_end))})
	row.job_order = doc.name
	row.accountant = doc.get("accountant")
	if doc.get("job_status") == "Finished":
		row.status = "Filed"
	elif row.status in (None, "", "Pending"):
		row.status = "Job Created"
	reg.save(ignore_permissions=True)


def seed_from_job_orders():
	"""One-time: build registers from existing VAT/CT Job Orders (parsing the period
	text). Safe to re-run."""
	jobs = frappe.get_all("Job Order",
	                      filters={"service": ["in", list(SERVICE_RULES)], "docstatus": ["<", 2]},
	                      fields=["name", "customer", "service", "company", "period", "accountant",
	                              "custom_period_end_date", "job_status"])
	made = 0
	for j in jobs:
		if not j.customer:
			continue
		if not (j.custom_period_end_date or parse_period_end(j.period)):
			continue
		sync_job_order(frappe._dict(j))
		made += 1
	frappe.db.commit()
	return made
