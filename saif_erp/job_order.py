# Copyright (c) 2026, SGA World FZ LLC and contributors
# For license information, please see license.txt
"""Job Order controller logic (ported from DB server scripts into app code)."""

import frappe

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
