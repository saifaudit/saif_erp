# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Move Credential Manager portal passwords from cleartext into Frappe's
encrypted password store, and mask the column. Idempotent and value-safe:
never logs or returns the secret; re-running skips already-masked rows."""

import frappe
from frappe.utils.password import set_encrypted_password


def execute():
	if not frappe.db.has_column("Credential Manager", "portal_password"):
		return
	rows = frappe.db.sql(
		"select name, portal_password from `tabCredential Manager` "
		"where portal_password is not null and portal_password != ''",
		as_dict=True,
	)
	migrated = 0
	for r in rows:
		pw = r.get("portal_password")
		# skip values already masked (all asterisks) — makes this idempotent
		if not pw or set(pw) <= {"*"}:
			continue
		set_encrypted_password("Credential Manager", r.name, pw, "portal_password")
		frappe.db.set_value("Credential Manager", r.name, "portal_password", "*" * len(pw), update_modified=False)
		migrated += 1
	frappe.db.commit()
	frappe.logger().info(f"Credential Manager: encrypted {migrated} portal passwords")
