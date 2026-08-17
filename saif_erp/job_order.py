# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Job Order controller logic (ported from DB server scripts into app code)."""

import frappe
from frappe import _

REVIEW_FIELDS = ("custom_reviewer_rating", "custom_review_remark")
# users granted the Reviewer role on install (override via site_config saif_reviewers)
DEFAULT_REVIEWERS = ["chandy@saifaudit.com", "santhosh@saifaudit.com"]


def reviewers():
	return frappe.conf.get("saif_reviewers") or DEFAULT_REVIEWERS


def enforce_review(doc, method=None):
	"""Guard the Job Order employee-review fields: only a user with the 'Reviewer'
	role (or Administrator) may set them; stamp who/when and validate 0–10."""
	prev = doc.get_doc_before_save()
	touched = any((not prev) or (prev.get(f) != doc.get(f)) for f in REVIEW_FIELDS)
	if not touched:
		return
	user = frappe.session.user
	if user != "Administrator" and "Reviewer" not in frappe.get_roles(user):
		frappe.throw(_("Only a Reviewer can set the employee review mark."))
	mark = frappe.utils.cint(doc.get("custom_reviewer_rating"))
	if mark:
		if mark < 0 or mark > 10:
			frappe.throw(_("Reviewer Mark must be between 0 and 10."))
		doc.custom_reviewed_by = user
		doc.custom_review_date = frappe.utils.nowdate()


# Approval Workflow state -> legacy approval_status (kept in sync for reports/number cards)
STATE_TO_APPROVAL = {
	"Draft": "Pending",
	"Pending Approval": "Pending",
	"Approved": "Approved",
	"Rejected": "Rejected",
}


def sync_approval_status(doc, method=None):
	"""Mirror the Job Order Approval workflow_state onto the legacy approval_status field.

	The formal Workflow drives ``workflow_state``; several existing reports and
	number cards still read ``approval_status``. Keep them consistent without a
	second manual step. Uses db_set so it is safe on submitted documents and
	bypasses permlevel restrictions on approval_status.
	"""
	target = STATE_TO_APPROVAL.get(doc.get("workflow_state"))
	if target and doc.get("approval_status") != target:
		doc.db_set("approval_status", target, update_modified=False)
