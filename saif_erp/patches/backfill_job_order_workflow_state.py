# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Backfill Job Order.workflow_state for records that predate the Job Order Approval workflow.

Idempotent: only fills blank/NULL workflow_state, so it is safe to re-run and safe to
apply to production's own live data at cutover.
"""

import frappe


def execute():
	if not frappe.db.has_column("Job Order", "workflow_state"):
		return

	# Submitted (1) and cancelled (2) job orders were all approved before submit.
	frappe.db.sql(
		"""
		UPDATE `tabJob Order`
		SET workflow_state = 'Approved'
		WHERE docstatus IN (1, 2) AND (workflow_state IS NULL OR workflow_state = '')
		"""
	)

	# Drafts awaiting the first approval.
	frappe.db.sql(
		"""
		UPDATE `tabJob Order`
		SET workflow_state = 'Pending Approval'
		WHERE docstatus = 0 AND (workflow_state IS NULL OR workflow_state = '')
		"""
	)

	# Keep the legacy approval_status field consistent with submitted state.
	frappe.db.sql(
		"""
		UPDATE `tabJob Order`
		SET approval_status = 'Approved'
		WHERE docstatus = 1 AND approval_status <> 'Approved'
		"""
	)
