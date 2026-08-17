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


@frappe.whitelist()
def make_job_order(source_name, target_doc=None):
	"""Pre-fill a new Job Order from an accepted Quotation (proposal), so Admin
	Support doesn't re-key the details. Opens a draft the user reviews + saves."""
	from frappe.model.mapper import get_mapped_doc

	def postprocess(source, target):
		target.quotation = source.name
		target.proposal_ref = source.get("ref_no") or source.name
		target.company = source.get("company")
		target.job_date = frappe.utils.nowdate()
		if source.get("quotation_to") == "Customer":
			target.customer = source.get("party_name")
		target.proposed_amount = source.get("grand_total")
		if source.get("items"):
			target.service = source.items[0].get("item_code")
		if source.get("custom_client_acceptance_notes"):
			target.job_status_remark = source.get("custom_client_acceptance_notes")

	return get_mapped_doc(
		"Quotation", source_name,
		{"Quotation": {"doctype": "Job Order"}},
		target_doc, postprocess,
	)
	# NB: the existing 'update Quotation when Job Order is created' server script
	# already links the proposal back on Job Order after_insert.


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
