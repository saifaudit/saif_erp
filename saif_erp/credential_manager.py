# Copyright (c) 2026, SGA World FZ LLC and contributors
"""Row-level access control for Credential Manager (client portal logins/passwords).

Plain accountants (Job Order Accountant) may only see/edit the credentials assigned
to them via the `accountant` field. Management-level roles see everything. Enforced
both for list views (permission_query_conditions) and single-doc access (has_permission).
"""

import frappe

# Roles that may see ALL credentials. Anyone with only "Job Order Accountant"
# (and none of these) is limited to their own assigned records.
FULL_ACCESS_ROLES = {
	"System Manager",
	"Job Order Admin",
	"Job Order Partner",
	"Job Order Semi Admin",
	"Job Order Admin Support",
}


def _has_full_access(user):
	if user == "Administrator":
		return True
	return bool(FULL_ACCESS_ROLES & set(frappe.get_roles(user)))


def get_permission_query_conditions(user=None):
	"""Limit the Credential Manager list to a plain accountant's own records."""
	user = user or frappe.session.user
	if _has_full_access(user):
		return ""
	return "`tabCredential Manager`.`accountant` = {}".format(frappe.db.escape(user))


def has_permission(doc, ptype=None, user=None, **kwargs):
	"""Gate single-doc read/write: a plain accountant only reaches their own."""
	user = user or frappe.session.user
	if _has_full_access(user):
		return True
	return doc.get("accountant") == user
