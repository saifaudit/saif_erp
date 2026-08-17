# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Admin Support (e.g. Allysa) had an over-broad role profile that exposed
salaries/all-HR and unrelated modules. Trim the 'SGASAIF-ADMIN-SUPPORT' profile to
what the role actually needs (create Job Orders + proposals) and re-sync its users.
Idempotent."""

import frappe

PROFILE = "SGASAIF-ADMIN-SUPPORT"
REMOVE = {"HR User", "Item Manager", "Purchase User", "Projects User", "Supplier", "Sales Manager"}


def execute():
	if not frappe.db.exists("Role Profile", PROFILE):
		return
	prof = frappe.get_doc("Role Profile", PROFILE)
	kept = [r for r in prof.roles if r.role not in REMOVE]
	if len(kept) != len(prof.roles):
		prof.set("roles", kept)
		prof.save(ignore_permissions=True)

	users = set(frappe.get_all("User", {"role_profile_name": PROFILE}, pluck="name"))
	users |= set(frappe.get_all("User Role Profile", {"role_profile": PROFILE, "parenttype": "User"}, pluck="parent"))
	for u in users:
		doc = frappe.get_doc("User", u)
		if hasattr(doc, "populate_role_profile_roles"):
			doc.populate_role_profile_roles()
		doc.save(ignore_permissions=True)
