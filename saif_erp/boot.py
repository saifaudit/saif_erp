# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Desk boot additions. Surfaces an employee-document alert (expired / expiring /
missing) to HR + management on every desk load — see public/js/doc_expiry_alert.js."""

import frappe

from saif_erp.document_expiry import get_expiring_documents

ALERT_ROLES = {"System Manager", "HR Manager", "HR User", "Job Order Admin", "Job Order Partner"}


def boot_session(bootinfo):
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		# Administrator still gets it if they hold a listed role below; skip Guest.
		if user == "Guest":
			return
	if not (ALERT_ROLES & set(frappe.get_roles(user))):
		return

	docs = get_expiring_documents(within_days=30)  # expired + expiring within 30 days
	expired = sum(1 for d in docs if d["days_left"] < 0)
	expiring = sum(1 for d in docs if 0 <= d["days_left"] <= 30)
	# "missing" = active employees with no passport expiry recorded (universal document)
	missing = frappe.db.count("Employee", {"status": "Active", "valid_upto": ["is", "not set"]})

	if expired or expiring or missing:
		bootinfo.doc_expiry_alert = {"expired": expired, "expiring": expiring, "missing": missing}
