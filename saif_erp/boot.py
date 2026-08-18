# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Desk boot additions — surfaces two desk-load alerts (see public/js/doc_expiry_alert.js):
an employee-document alert (HR/management firm-wide, employees their own) and a
compliance-filings alert (management firm-wide, accountants their own)."""

import frappe

from saif_erp.document_expiry import get_expiring_documents

ALERT_ROLES = {"System Manager", "HR Manager", "HR User", "Job Order Admin",
               "Job Order Partner", "Job Order Admin Support"}
FILING_MGMT_ROLES = {"System Manager", "Job Order Admin", "Job Order Partner", "Job Order Admin Support"}


def boot_session(bootinfo):
	user = frappe.session.user
	if user == "Guest":
		return
	roles = set(frappe.get_roles(user))
	_document_alert(bootinfo, user, roles)
	_compliance_alert(bootinfo, user, roles)


def _document_alert(bootinfo, user, roles):
	if ALERT_ROLES & roles:
		# HR / management: firm-wide
		docs = get_expiring_documents(within_days=30)
		expired = sum(1 for d in docs if d["days_left"] < 0)
		expiring = sum(1 for d in docs if 0 <= d["days_left"] <= 30)
		missing = frappe.db.count("Employee", {"status": "Active", "valid_upto": ["is", "not set"]})
		if expired or expiring or missing:
			bootinfo.doc_expiry_alert = {"self": 0, "expired": expired, "expiring": expiring, "missing": missing}
		return
	# everyone else: their OWN documents only
	emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not emp:
		return
	mine = get_expiring_documents(within_days=30, employee=emp, active_only=False)
	expired = sum(1 for d in mine if d["days_left"] < 0)
	expiring = sum(1 for d in mine if 0 <= d["days_left"] <= 30)
	if expired or expiring:
		bootinfo.doc_expiry_alert = {"self": 1, "expired": expired, "expiring": expiring, "missing": 0}


def _compliance_alert(bootinfo, user, roles):
	from saif_erp.compliance import get_open_filings
	is_mgmt = bool(FILING_MGMT_ROLES & roles)
	fils = get_open_filings(within_days=30, include_overdue=True) if is_mgmt \
		else get_open_filings(accountant=user, within_days=30, include_overdue=True)
	overdue = sum(1 for f in fils if f["days_left"] < 0)
	soon = sum(1 for f in fils if 0 <= f["days_left"] <= 30)
	if overdue or soon:
		bootinfo.compliance_alert = {"self": 0 if is_mgmt else 1, "overdue": overdue, "soon": soon}
