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


# ---------------------------------------------------------------------------
# Job Order progress / stage tracking (SGA desk process — no fieldwork).
# Derived from fields already captured across the lifecycle, so there is no
# separate checklist table and no double entry. See the confirmed process doc.
# ---------------------------------------------------------------------------
# Friendly "current activity" label for the gap AFTER each reached WORK milestone.
# Payment is NOT a linear stage (it can be an early advance) — it only gates
# delivery-readiness (delivery is made on/after full payment).
_NEXT_STAGE = {
	"Approved": "Work in progress",
	"Sent for review": "In review",
	"Reviewed": "Ready — send draft to client",
	"Draft sent to client": "Awaiting client draft approval",
	"Draft approved": "Ready to print",          # audit: only reached before printing
}


def _is_audit(doc):
	return "audit" in (doc.get("service") or "").lower()


def _milestones(doc):
	"""Ordered WORK checkpoints (label, done?). 'Report printed' applies to audit
	jobs only (only audit reports are printed). Payment is handled separately."""
	js = doc.get("job_status")
	m = [
		("Approved", doc.get("approval_status") == "Approved"),
		("Sent for review", js == "Under Review" or bool(doc.get("custom_review_date"))),
		("Reviewed", bool(doc.get("custom_review_date") or doc.get("custom_reviewer_rating"))),
		("Draft sent to client", bool(doc.get("draft_sent_date"))),
		("Draft approved", bool(doc.get("draft_approved_date"))),
	]
	if _is_audit(doc):
		m.append(("Report printed", bool(doc.get("report_printed"))))
	# report_delivery_status is a Yes/No field ("No" is not "delivered")
	m.append(("Delivered", doc.get("report_delivery_status") == "Yes" or bool(doc.get("report_delivery_date"))))
	return m


def compute_stage(doc, method=None):
	"""Set custom_stage + custom_progress from the lifecycle fields. Runs on
	on_update and on_update_after_submit (most progress happens post-submit)."""
	m = _milestones(doc)
	labels = [x[0] for x in m]
	total = len(m)
	furthest = -1
	for i, (_lbl, done) in enumerate(m):
		if done:
			furthest = i
	paid = doc.get("payment_status") == "Paid"
	delivered = m[-1][1]
	js = doc.get("job_status")

	if js == "Closed (Failed)":
		stage, pct = "Closed (Failed)", 100
	elif js == "Finished":                           # terminal work status
		stage, pct = ("Delivered — complete" if delivered else "Finished — complete"), 100
	elif furthest == total - 1:                      # Delivered
		stage, pct = "Delivered — complete", 100
	elif furthest < 0:
		stage, pct = "Pending approval", 0
	elif furthest == total - 2:                      # deliverable ready (draft approved / printed)
		stage = "Ready for delivery" if paid else "Awaiting payment"
		pct = round((furthest + 1) / total * 100)
	else:
		stage = _NEXT_STAGE.get(labels[furthest], labels[furthest])
		pct = round((furthest + 1) / total * 100)

	# stalled jobs (paused / waiting on the client) surface as their own stage
	if stage == "Work in progress" and js in ("Temporarily stopped", "Awaiting Client Data"):
		stage = "On hold / awaiting client"

	# auto-stamp who sent the draft
	if doc.get("draft_sent_date") and not doc.get("draft_sent_by"):
		doc.db_set("draft_sent_by", frappe.session.user, update_modified=False)
	if doc.get("custom_stage") != stage:
		doc.db_set("custom_stage", stage, update_modified=False)
	if frappe.utils.cint(doc.get("custom_progress")) != int(pct):
		doc.db_set("custom_progress", int(pct), update_modified=False)


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
