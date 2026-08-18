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


# (label, min_days, max_days, hex_colour, frappe_indicator) — None = open-ended
FILING_BANDS = [
	("Overdue", None, -1, "#8b1a1a", "Red"),
	("≤ 30 days", 0, 30, "#e0533d", "Red"),
	("31 – 60 days", 31, 60, "#e8804d", "Orange"),
	("61 – 90 days", 61, 90, "#e6a817", "Orange"),
	("> 90 days", 91, None, "#22a06b", "Green"),
]


def filing_band(days):
	for label, lo, hi, color, ind in FILING_BANDS:
		if lo is None:
			if days <= hi:
				return label, color, ind
		elif hi is None:
			if days >= lo:
				return label, color, ind
		elif lo <= days <= hi:
			return label, color, ind
	return FILING_BANDS[-1][0], FILING_BANDS[-1][3], FILING_BANDS[-1][4]


def get_open_filings(accountant=None, within_days=None, include_overdue=True):
	"""Open filing periods (not yet Filed) from ACTIVE registers, soonest due first,
	with days-to-due and an urgency band. accountant scopes to one person."""
	conds = ["cr.active = 1", "cfp.status in ('Pending','Job Created')", "cfp.due_date is not null"]
	params = {}
	if accountant:
		conds.append("cfp.accountant = %(acc)s")
		params["acc"] = accountant
	rows = frappe.db.sql(
		f"""select cr.name register, cr.customer, cr.customer_name, cr.service, cr.company,
			cfp.period_label, cfp.period_end_date, cfp.due_date, cfp.status,
			cfp.job_order, cfp.accountant, datediff(cfp.due_date, curdate()) days_left
		from `tabCompliance Filing Period` cfp
		join `tabCompliance Register` cr on cr.name = cfp.parent
		where {' and '.join(conds)}
		order by cfp.due_date""",
		params, as_dict=True,
	)
	out = []
	for r in rows:
		if within_days is not None and r.days_left > within_days:
			continue
		if not include_overdue and r.days_left < 0:
			continue
		r["band"], r["_color"], r["indicator"] = filing_band(r.days_left)
		out.append(r)
	return out


def _accountant_ok(user):
	"""The assigned accountant is a valid recipient only if their login is enabled and
	their Employee (if any) is still Active — i.e. not resigned."""
	if not user or not frappe.db.get_value("User", user, "enabled"):
		return False
	status = frappe.db.get_value("Employee", {"user_id": user}, "status")
	return status in (None, "Active")


def _manager_recipients():
	users = frappe.get_all("Has Role",
	                       {"role": ["in", ["Job Order Admin", "Job Order Partner"]], "parenttype": "User"},
	                       pluck="parent")
	users = [u for u in set(users) if "@" in u and u not in ("Administrator", "Guest")]
	return users or ["santhosh@saifaudit.com"]


def notify_compliance_deadlines():
	"""Daily reminder: email the current accountant + info@ (+ manager fallback if the
	accountant has resigned) 30/15/7 days before each filing's due date. Dormant on the
	local bench (scheduler + email off); fires on production."""
	reminder_days = frappe.conf.get("saif_compliance_reminder_days") or REMINDER_DAYS
	info = frappe.conf.get("saif_compliance_info_email") or "info@saifaudit.com"
	for f in get_open_filings(within_days=max(reminder_days), include_overdue=False):
		if f["days_left"] not in reminder_days:
			continue
		recipients = []
		if _accountant_ok(f.get("accountant")):
			recipients.append(f["accountant"])
		else:
			recipients += _manager_recipients()  # resigned/disabled -> escalate
		if info and info not in recipients:
			recipients.append(info)
		if not recipients:
			continue
		subject = "Filing due in {n} days: {svc} — {cust}".format(
			n=f["days_left"], svc=f["service"], cust=f["customer_name"] or f["customer"])
		message = frappe.render_template(
			"""<p>A statutory filing is due soon.</p>
			<table cellpadding="6" style="border-collapse:collapse">
			<tr><td><b>Client</b></td><td>{{ cust }}</td></tr>
			<tr><td><b>Service</b></td><td>{{ svc }}</td></tr>
			<tr><td><b>Period</b></td><td>{{ period }}</td></tr>
			<tr><td><b>Due date</b></td><td>{{ due }}</td></tr>
			<tr><td><b>Days remaining</b></td><td style="color:#c1272d"><b>{{ n }}</b></td></tr>
			<tr><td><b>Job Order</b></td><td>{{ jo or "—" }}</td></tr>
			</table>
			<p>Please complete and file before the due date.</p>""",
			{"cust": f["customer_name"] or f["customer"], "svc": f["service"],
			 "period": f["period_label"], "due": frappe.utils.formatdate(f["due_date"]),
			 "n": f["days_left"], "jo": f.get("job_order")},
		)
		frappe.sendmail(recipients=recipients, subject=subject, message=message,
		                reference_doctype="Compliance Register", reference_name=f["register"])


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
