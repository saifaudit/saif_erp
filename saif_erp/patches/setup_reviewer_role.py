# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Create the 'Reviewer' role and grant it to the configured reviewers, so the
Job Order employee-review mark is role-gated (add/remove reviewers by assigning
the role, no code change). Idempotent."""

import frappe

from saif_erp.job_order import reviewers


def execute():
	if not frappe.db.exists("Role", "Reviewer"):
		frappe.get_doc({"doctype": "Role", "role_name": "Reviewer", "desk_access": 1}).insert(
			ignore_permissions=True)
	for user in reviewers():
		if frappe.db.exists("User", user) and not frappe.db.exists(
			"Has Role", {"parent": user, "parenttype": "User", "role": "Reviewer"}
		):
			frappe.get_doc("User", user).add_roles("Reviewer")
